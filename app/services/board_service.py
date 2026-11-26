"""計画ボード用のデータ（DayPilot Scheduler 向けに整形）。

時刻はすべて拠点の現地時刻（オフセットなしの ISO 文字列）で返す。DayPilot は
タイムゾーンを持たない日時で描画するため、変換はサーバー側で行う。
"""
from collections import defaultdict
from datetime import date, datetime, time, timedelta

from sqlalchemy import false, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.timeutil import to_jst_naive, as_jst, weekday_number
from app.engine.day_problem import QTY_SCALE
from app.engine.day_snapshot import build_day_problem
from app.engine.kpi_keys import normalize_kpis
from app.engine.snapshot import build_problem
from app.engine.weekdays import DAY_NAMES
from app.models.masters import (
    CalculationSetting,
    Location,
    ProcessGroup,
    Product,
    ProductProcess,
    Resource,
    ResourceGroup,
    WorkerSkillMap,
)
from app.models.transactions import Order, Plan, PlanAssignment, PlanKpi, PlanViolation, Task
from app.schemas.base import coerce
from app.services.plan_lifecycle import blocks_plan_approval
from app.services.worktime import gaps

SEVERITY_ORDER = {"HARD": 0, "SOFT": 1, "INFO": 2}

# 現行Excelの1文字見出しに合わせた主要工程の略称。該当しない工程は先頭2文字を使う。
PROCESS_SHORT_LABELS = {
    "ピッキング": "ピ",
    "本体組立": "組",
    "組立": "組",
    "電気調整": "電",
    "エイジング": "エ",
    "エージング": "エ",
    "校正": "校",
    "ガス校正": "校",
    "出荷準備": "出",
    "梱包": "梱",
    "リークテスト": "リ",
}


# 日本時間の日時を、拠点の現地時刻を表す文字列へ変換する。
def _local(dt: datetime, tz: str) -> str:
    return as_jst(dt).replace(tzinfo=None).isoformat(timespec="seconds")


# 工程名からExcel風一覧の短い列見出しを返す。
def _short_process_label(name: str) -> str:
    if name in PROCESS_SHORT_LABELS:
        return PROCESS_SHORT_LABELS[name]
    return name[:2]


# 稼働日・作業者軸のボード情報と、Excel風オーダー一覧・日別作業者負荷データを組み立てる。
def _build_day_board(db: Session, plan: Plan, start: datetime, end: datetime, tz: str) -> dict:
    problem = build_day_problem(db, plan)

    # ---- 工程区分マスタ（表示順と名称の参照用）
    pg_rows = db.scalars(
        select(ProcessGroup)
        .where(ProcessGroup.LocationID == plan.LocationID, ProcessGroup.DeleteFlag == false())
        .order_by(ProcessGroup.SortOrder, ProcessGroup.ProcessGroupID)
    ).all()
    pg_map = {g.ProcessGroupID: g for g in pg_rows}

    # ---- 作業者ごとの主担当工程区分をスキルマップから推定し、作業者ボードの並び順・区分見出しに使う
    worker_pg_counts: dict[int, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    skill_rows = db.execute(
        select(WorkerSkillMap.WorkerID, ProductProcess.ProcessGroupID)
        .join(ProductProcess, ProductProcess.ProductProcessID == WorkerSkillMap.ProductProcessID)
        .where(
            WorkerSkillMap.WorkerID.in_(list(problem.workers.keys()) or [-1]),
            WorkerSkillMap.CanExecute == True,  # noqa: E712
            ProductProcess.ProcessGroupID.is_not(None),
        )
    ).all()
    for wid, pg_id in skill_rows:
        worker_pg_counts[wid][pg_id] += 1

    worker_primary_pg: dict[int, int | None] = {}
    for wid in problem.workers:
        counts = worker_pg_counts.get(wid)
        if counts:
            # 担当工程数が最も多い区分を採用し、同数は工程区分の表示順で揃える。
            worker_primary_pg[wid] = min(
                counts.keys(),
                key=lambda gid: (-counts[gid], pg_map[gid].SortOrder if gid in pg_map else 9999, gid),
            )
        else:
            worker_primary_pg[wid] = None

    sorted_workers = sorted(
        problem.workers.values(),
        key=lambda w: (
            pg_map[worker_primary_pg[w.id]].SortOrder if worker_primary_pg[w.id] in pg_map else 9999,
            w.id,
        ),
    )

    resources = []
    for w in sorted_workers:
        gid = worker_primary_pg[w.id]
        gname = pg_map[gid].ProcessGroupName if gid in pg_map else None
        max_qty = round(w.max_daily_qty / QTY_SCALE, 3) if w.max_daily_qty is not None else None
        resources.append({
            "id": w.id,
            "name": w.name,
            "capacity": max_qty or 0,
            "maxDailyQuantity": max_qty,
            "groupId": gid,
            "groupName": gname,
        })

    group_list = []
    for r in resources:
        if not group_list or group_list[-1]["id"] != r["groupId"]:
            group_list.append({"id": r["groupId"], "name": r["groupName"], "resourceIds": []})
        group_list[-1]["resourceIds"].append(r["id"])

    # ---- 課題と割付済みタスクの集計
    assign_rows = db.scalars(select(PlanAssignment).where(PlanAssignment.PlanID == plan.PlanID)).all()
    assign_by_task = {a.TaskID: a for a in assign_rows}
    assigned = set(assign_by_task.keys())

    issues = db.scalars(select(PlanViolation).where(PlanViolation.PlanID == plan.PlanID)).all()
    worst: dict[int, str] = {}
    for v in issues:
        if v.TaskID is not None and SEVERITY_ORDER[v.Severity] < SEVERITY_ORDER.get(worst.get(v.TaskID, "INFO"), 3):
            worst[v.TaskID] = v.Severity

    # ---- オーダー・製品の補助情報（納品先・製品名）をまとめて取得
    order_ids = list(problem.orders.keys())
    order_rows = {
        o.OrderID: o
        for o in db.scalars(select(Order).where(Order.OrderID.in_(order_ids or [-1])))
    }
    product_ids = {o.ProductID for o in order_rows.values() if o.ProductID is not None}
    product_map = {
        p.ProductID: p
        for p in db.scalars(select(Product).where(Product.ProductID.in_(list(product_ids) or [-1])))
    }

    # ---- イベント（作業者ガント表示用）
    events = []
    for a in sorted(assign_rows, key=lambda x: (x.WorkerID or 0, x.StartAt, x.TaskID)):
        if a.WorkerID is None or a.WorkerID not in problem.workers:
            continue
        if not (a.StartAt < end and a.EndAt > start):
            continue
        task = problem.tasks.get(a.TaskID)
        if task is None:
            continue
        dorder = problem.orders.get(task.order_id)
        if dorder is None:
            continue
        raw_order = order_rows.get(dorder.id)
        prod = product_map.get(dorder.product_id) if dorder.product_id is not None else None
        worker = problem.workers[a.WorkerID]
        res_obj = problem.resources.get(a.ResourceID) if a.ResourceID is not None else None
        qty_val = coerce(raw_order.Quantity) if raw_order else None
        events.append({
            "id": a.AssignmentID,
            "resource": a.WorkerID,
            "workerId": a.WorkerID,
            "workerName": worker.name,
            "resourceId": a.ResourceID,
            "resourceName": res_obj.name if res_obj else None,
            "requiresResource": task.requires_resource,
            "eligibleResourceIds": task.eligible_resource_ids,
            "start": _local(a.StartAt, tz),
            "end": _local(a.EndAt, tz),
            "text": f"{dorder.no} {task.process_name}",
            "taskId": task.id,
            "orderId": dorder.id,
            "wbsNumber": dorder.no,
            "taskName": task.process_name,
            "productName": prod.ProductName if prod else None,
            "quantity": qty_val,
            "deadLine": _local(raw_order.DeadLine, tz) if raw_order and raw_order.DeadLine else None,
            "shippingDate": _local(raw_order.ShippingDate, tz) if raw_order and raw_order.ShippingDate else None,
            "isLocked": a.IsLocked,
            "source": a.Source,
            "setupMinutes": 0,
            "colorValue": str(dorder.product_id) if dorder.product_id is not None else dorder.no,
            "issue": worst.get(task.id),
            "rowVer": a.RowVer,
        })

    # ---- 作業者別の非稼働日（拠点休日＋本人の全日不在日を網掛け）
    non_working = []
    cur_date = start.date()
    last_date = (end - timedelta(seconds=1)).date() if end > start else cur_date
    all_dates: list[date] = []
    while cur_date <= last_date:
        all_dates.append(cur_date)
        cur_date += timedelta(days=1)
    for w in sorted_workers:
        for d in all_dates:
            d_idx = problem.date_to_ext_idx.get(d)
            if d_idx is None or d_idx not in w.available_days:
                d0 = datetime.combine(d, time(0, 0))
                d1 = datetime.combine(d + timedelta(days=1), time(0, 0))
                non_working.append({
                    "resource": w.id,
                    "start": _local(d0, tz),
                    "end": _local(d1, tz),
                })

    # ---- 未割付タスク（durations に実行可能作業者ID→所要稼働日数を設定）
    unscheduled = []
    for task in problem.tasks.values():
        if task.id in assigned:
            continue
        dorder = problem.orders[task.order_id]
        raw_order = order_rows.get(dorder.id)
        ship_or_due = (raw_order.ShippingDate or raw_order.DeadLine) if raw_order else None
        unscheduled.append({
            "taskId": task.id,
            "orderId": task.order_id,
            "wbsNumber": dorder.no,
            "name": task.name,
            "durations": {str(wid): task.duration_days for wid in task.eligible_worker_ids},
            "requiresResource": task.requires_resource,
            "eligibleResourceIds": task.eligible_resource_ids,
            "deadLine": _local(ship_or_due, tz) if ship_or_due else None,
            "colorValue": str(dorder.product_id) if dorder.product_id is not None else dorder.no,
        })

    # ---- Excel風一覧ビュー（オーダー行 × 工程列）と作業者別・日別の台数サマリ
    # 工程列キー: "{processGroupId or 0}:{processName}" として工程区分順に並べる。
    col_meta: dict[str, tuple[int, int, str, int | None, str | None]] = {}
    for task in problem.tasks.values():
        key = f"{task.process_group_id or 0}:{task.process_name}"
        pg_sort = pg_map[task.process_group_id].SortOrder if task.process_group_id in pg_map else 9999
        pg_name = pg_map[task.process_group_id].ProcessGroupName if task.process_group_id in pg_map else None
        if key not in col_meta:
            col_meta[key] = (pg_sort, task.sequence_number, task.process_name, task.process_group_id, pg_name)
        else:
            prev = col_meta[key]
            col_meta[key] = (min(prev[0], pg_sort), min(prev[1], task.sequence_number), prev[2], prev[3], prev[4])

    process_columns = [
        {
            "key": key,
            "label": pname,
            "shortLabel": _short_process_label(pname),
            "processGroupId": pg_id,
            "processGroupName": pg_name,
        }
        for key, (_pg_s, _seq, pname, pg_id, pg_name) in sorted(
            col_meta.items(), key=lambda item: (item[1][0], item[1][1], item[1][2])
        )
    ]

    tasks_by_order: dict[int, list] = defaultdict(list)
    for task in problem.tasks.values():
        tasks_by_order[task.order_id].append(task)

    daily_orders = []
    sorted_orders = sorted(
        problem.orders.values(),
        key=lambda o: (o.shipping_date or date.max, o.no, o.id),
    )
    for dorder in sorted_orders:
        otasks = sorted(tasks_by_order.get(dorder.id, []), key=lambda t: (t.sequence_number, t.id))
        # タスク未生成のオーダーは計画対象外のためExcel風一覧には含めない。
        if not otasks:
            continue
        raw_order = order_rows.get(dorder.id)
        prod = product_map.get(dorder.product_id) if dorder.product_id is not None else None
        cells: dict[str, dict] = {}
        worker_names_ordered: list[str] = []
        max_end_idx: int | None = None

        for task in otasks:
            col_key = f"{task.process_group_id or 0}:{task.process_name}"
            a = assign_by_task.get(task.id)
            std_date = (
                problem.ext_idx_to_date.get(task.standard_day_idx)
                if task.standard_day_idx is not None
                else None
            )
            if a is not None:
                s_idx = problem.dt_to_day_idx(a.StartAt)
                e_idx = problem.end_dt_to_day_idx(a.EndAt)
                if e_idx is not None:
                    max_end_idx = e_idx if max_end_idx is None else max(max_end_idx, e_idx)
                shift_days = (
                    (s_idx - task.standard_day_idx)
                    if s_idx is not None and task.standard_day_idx is not None
                    else None
                )
                wname = problem.workers[a.WorkerID].name if a.WorkerID in problem.workers else None
                res_obj = problem.resources.get(a.ResourceID) if a.ResourceID is not None else None
                if wname and wname not in worker_names_ordered:
                    worker_names_ordered.append(wname)
                end_disp_date = (
                    (a.EndAt - timedelta(seconds=1)).date()
                    if a.EndAt.time() == time(0, 0)
                    else a.EndAt.date()
                )
                cells[col_key] = {
                    "taskId": task.id,
                    "assignmentId": a.AssignmentID,
                    "rowVer": a.RowVer,
                    "workerId": a.WorkerID,
                    "workerName": wname,
                    "resourceId": a.ResourceID,
                    "resourceName": res_obj.name if res_obj else None,
                    "requiresResource": task.requires_resource,
                    "eligibleResourceIds": task.eligible_resource_ids,
                    "date": a.StartAt.date().isoformat(),
                    "endDate": end_disp_date.isoformat(),
                    "label": a.StartAt.strftime("%m/%d"),
                    "standardDate": std_date.isoformat() if std_date else None,
                    "shiftDays": shift_days,
                    "isLocked": bool(a.IsLocked),
                    "issue": worst.get(task.id),
                    "eligibleWorkerIds": task.eligible_worker_ids,
                }
            else:
                cells[col_key] = {
                    "taskId": task.id,
                    "assignmentId": None,
                    "rowVer": None,
                    "workerId": None,
                    "workerName": None,
                    "resourceId": None,
                    "resourceName": None,
                    "requiresResource": task.requires_resource,
                    "eligibleResourceIds": task.eligible_resource_ids,
                    "date": None,
                    "endDate": None,
                    "label": "未割付",
                    "standardDate": std_date.isoformat() if std_date else None,
                    "shiftDays": None,
                    "isLocked": False,
                    "issue": worst.get(task.id),
                    "eligibleWorkerIds": task.eligible_worker_ids,
                }

        is_late = (
            dorder.shipping_day_idx is not None
            and max_end_idx is not None
            and max_end_idx > dorder.shipping_day_idx - 1
        )
        ship_d = dorder.shipping_date
        daily_orders.append({
            "orderId": dorder.id,
            "wbsNumber": dorder.no,
            "customerName": raw_order.CustomerName if raw_order else None,
            "productName": prod.ProductName if prod else None,
            "orderName": dorder.name,
            "quantity": coerce(raw_order.Quantity) if raw_order else None,
            "excludeFromDailyCap": dorder.exclude_from_daily_cap,
            "shippingDate": ship_d.isoformat() if ship_d else None,
            "shippingLabel": ship_d.strftime("%m/%d") if ship_d else "—",
            "shippingWeekday": DAY_NAMES[weekday_number(ship_d)] if ship_d else "",
            "late": is_late,
            "workerSummary": " / ".join(worker_names_ordered),
            "cells": cells,
        })

    # 作業者×稼働日ごとの1日作業台数負荷を集計（日上限カウント対象の先頭工程のみ）
    load_scaled: dict[tuple[int, int], int] = defaultdict(int)
    for a in assign_rows:
        if a.WorkerID is None:
            continue
        task = problem.tasks.get(a.TaskID)
        if task is None or not task.counts_for_daily_cap:
            continue
        dorder = problem.orders.get(task.order_id)
        if dorder is None or dorder.quantity_scaled <= 0:
            continue
        s_idx = problem.dt_to_day_idx(a.StartAt)
        e_idx = problem.end_dt_to_day_idx(a.EndAt)
        if s_idx is None or e_idx is None:
            continue
        for d_idx in range(s_idx, e_idx + 1):
            if 0 <= d_idx < problem.num_days:
                load_scaled[(a.WorkerID, d_idx)] += dorder.quantity_scaled

    working_days_view = [
        {
            "date": d.isoformat(),
            "label": d.strftime("%m/%d"),
            "weekday": DAY_NAMES[weekday_number(d)],
        }
        for d in problem.working_days
    ]
    worker_loads = []
    for w in sorted_workers:
        gid = worker_primary_pg[w.id]
        gname = pg_map[gid].ProcessGroupName if gid in pg_map else None
        max_qty = round(w.max_daily_qty / QTY_SCALE, 3) if w.max_daily_qty is not None else None
        loads_by_date: dict[str, dict] = {}
        for d_idx, d in enumerate(problem.working_days):
            used_s = load_scaled.get((w.id, d_idx), 0)
            loads_by_date[d.isoformat()] = {
                "used": round(used_s / QTY_SCALE, 3),
                "available": d_idx in w.available_days,
                "over": w.max_daily_qty is not None and used_s > w.max_daily_qty,
            }
        worker_loads.append({
            "workerId": w.id,
            "workerName": w.name,
            "groupName": gname,
            "maxDailyQuantity": max_qty,
            "loads": loads_by_date,
        })

    # 拠点のリソース一覧と、リソース×稼働日ごとの台数・同時タスク件数サマリを構築する。
    equipment_resources = [
        {
            "id": r.id,
            "name": r.name,
            "groupId": r.group_id,
            "groupName": r.group_name,
            "dailyCapacityQuantity": round(r.daily_capacity_qty / QTY_SCALE, 3) if r.daily_capacity_qty is not None else None,
            "capacity": r.capacity,
        }
        for r in problem.resources.values()
    ]
    res_qty_scaled: dict[tuple[int, int], int] = defaultdict(int)
    res_cnt: dict[tuple[int, int], int] = defaultdict(int)
    for a in assign_rows:
        if a.ResourceID is None or a.ResourceID not in problem.resources:
            continue
        task = problem.tasks.get(a.TaskID)
        if task is None:
            continue
        dorder = problem.orders.get(task.order_id)
        qty_s = dorder.quantity_scaled if dorder is not None and dorder.quantity_scaled > 0 else 0
        s_idx = problem.dt_to_day_idx(a.StartAt)
        e_idx = problem.end_dt_to_day_idx(a.EndAt)
        if s_idx is None or e_idx is None:
            continue
        for d_idx in range(s_idx, e_idx + 1):
            if 0 <= d_idx < problem.num_days:
                res_cnt[(a.ResourceID, d_idx)] += 1
                if qty_s > 0:
                    res_qty_scaled[(a.ResourceID, d_idx)] += qty_s

    resource_loads = []
    for r in problem.resources.values():
        max_qty = round(r.daily_capacity_qty / QTY_SCALE, 3) if r.daily_capacity_qty is not None else None
        r_loads_by_date: dict[str, dict] = {}
        for d_idx, d in enumerate(problem.working_days):
            used_s = res_qty_scaled.get((r.id, d_idx), 0)
            used_c = res_cnt.get((r.id, d_idx), 0)
            over_qty = r.daily_capacity_qty is not None and used_s > r.daily_capacity_qty
            over_cnt = r.capacity is not None and used_c > r.capacity
            r_loads_by_date[d.isoformat()] = {
                "usedQty": round(used_s / QTY_SCALE, 3),
                "usedCount": used_c,
                "over": over_qty or over_cnt,
            }
        resource_loads.append({
            "resourceId": r.id,
            "resourceName": r.name,
            "groupName": r.group_name,
            "dailyCapacityQuantity": max_qty,
            "capacity": r.capacity,
            "loads": r_loads_by_date,
        })

    kpis = normalize_kpis({
        k.KpiKey: coerce(k.KpiValue)
        for k in db.scalars(select(PlanKpi).where(PlanKpi.PlanID == plan.PlanID))
    })
    return {
        "plan": {
            "planId": plan.PlanID,
            "planName": plan.PlanName,
            "status": plan.Status,
            "timeUnit": "DAY",
            "startAt": _local(plan.StartAt, tz),
            "endAt": _local(plan.EndAt, tz),
            "rowVer": plan.RowVer,
        },
        "timeZone": tz,
        "from": _local(start, tz),
        "to": _local(end, tz),
        "groups": group_list,
        "resources": resources,
        "events": events,
        "setups": [],
        "nonWorking": non_working,
        "unscheduled": unscheduled,
        "issues": [
            {
                "severity": v.Severity,
                "message": v.Message,
                "taskId": v.TaskID,
                "blocksApproval": blocks_plan_approval(v, assigned),
            }
            for v in sorted(issues, key=lambda v: (SEVERITY_ORDER[v.Severity], v.ViolationID))
        ],
        "kpis": kpis,
        "dailyView": {
            "workingDays": working_days_view,
            "processColumns": process_columns,
            "orders": daily_orders,
            "workerLoads": worker_loads,
            "equipmentResources": equipment_resources,
            "resourceLoads": resource_loads,
        },
    }


# 計画の拠点に属する設備・割付・違反情報をボード表示用にまとめる。
def build_board(
    db: Session,
    plan: Plan,
    start: datetime | None = None,
    end: datetime | None = None,
    resource_group_id: int | None = None,
) -> dict:
    # 対象の拠点と、アプリ共通の時刻設定。
    location = db.get(Location, plan.LocationID)
    tz = get_settings().app_timezone
    start = to_jst_naive(start) if start else plan.StartAt
    end = to_jst_naive(end) if end else plan.EndAt
    # 日単位計算の計画は、作業者軸ガント＋Excel風一覧用のデータ構造を返す。
    setting = db.get(CalculationSetting, plan.CalculationSettingID)
    if setting and setting.TimeUnit == "DAY":
        return _build_day_board(db, plan, start, end, tz)
    problem = build_problem(db, plan)

    # ---- リソース（グループ順・表示順）
    groups = {g.ResourceGroupID: g for g in db.scalars(select(ResourceGroup).where(ResourceGroup.LocationID == location.LocationID))}
    res_rows = db.scalars(
        select(Resource).where(Resource.LocationID == location.LocationID, Resource.DeleteFlag == false())
    ).all()
    if resource_group_id is not None:
        res_rows = [r for r in res_rows if r.ResourceGroupID == resource_group_id]
    # コード廃止後もグループ順・設備の表示順を優先し、同順は名前とIDで揃える。
    res_rows.sort(key=lambda r: (groups[r.ResourceGroupID].SortOrder if r.ResourceGroupID in groups else 9999,
                                 r.SortOrder, r.ResourceName, r.ResourceID))
    resource_ids = {r.ResourceID for r in res_rows}
    resources = [
        {
            "id": r.ResourceID, "name": r.ResourceName,
            "capacity": coerce(r.Capacity), "groupId": r.ResourceGroupID,
            "groupName": groups[r.ResourceGroupID].GroupName if r.ResourceGroupID in groups else None,
        }
        for r in res_rows
    ]
    group_list = []
    for r in resources:
        if not group_list or group_list[-1]["id"] != r["groupId"]:
            group_list.append({"id": r["groupId"], "name": r["groupName"], "resourceIds": []})
        group_list[-1]["resourceIds"].append(r["id"])

    # 表示期間や設備の絞り込みに左右されない、計画全体の割付済みタスク。
    assigned = set(db.scalars(select(PlanAssignment.TaskID).where(PlanAssignment.PlanID == plan.PlanID)))

    # ---- 課題（タスク別の最も重い違反）
    issues = db.scalars(select(PlanViolation).where(PlanViolation.PlanID == plan.PlanID)).all()
    worst: dict[int, str] = {}
    for v in issues:
        if v.TaskID is not None and SEVERITY_ORDER[v.Severity] < SEVERITY_ORDER.get(worst.get(v.TaskID, "INFO"), 3):
            worst[v.TaskID] = v.Severity

    # ---- イベント（割付）と段取りブロック
    rows = db.execute(
        select(PlanAssignment, Task, Order, Product)
        .join(Task, Task.TaskID == PlanAssignment.TaskID)
        .join(Order, Order.OrderID == Task.OrderID)
        .outerjoin(Product, Product.ProductID == Order.ProductID)
        .where(PlanAssignment.PlanID == plan.PlanID, PlanAssignment.StartAt < end, PlanAssignment.EndAt > start)
        .order_by(PlanAssignment.ResourceID, PlanAssignment.StartAt)
    ).all()
    events, setups = [], []
    for a, t, j, product in rows:
        if a.ResourceID not in resource_ids:
            continue
        events.append({
            "id": a.AssignmentID, "resource": a.ResourceID,
            "start": _local(a.StartAt, tz), "end": _local(a.EndAt, tz),
            "text": f"{j.WBSNumber} {t.TaskName}",
            "taskId": t.TaskID, "orderId": j.OrderID, "wbsNumber": j.WBSNumber, "taskName": t.TaskName,
            "productName": product.ProductName if product else None,
            "quantity": coerce(j.Quantity),
            "deadLine": _local(j.DeadLine, tz) if j.DeadLine else None,
            "isLocked": a.IsLocked, "source": a.Source, "setupMinutes": a.SetupMinutes,
            # 製品ごとの配色を維持し、製品未指定時はオーダー番号を使う。
            "colorValue": str(j.ProductID) if j.ProductID is not None else j.WBSNumber,
            "issue": worst.get(t.TaskID), "rowVer": a.RowVer,
        })
        if a.SetupMinutes:
            setups.append({
                "id": f"setup-{a.AssignmentID}", "resource": a.ResourceID,
                "start": _local(problem.to_dt(problem.to_min(a.StartAt) - a.SetupMinutes), tz),
                "end": _local(a.StartAt, tz), "minutes": a.SetupMinutes,
            })

    # ---- 非稼働時間（セルの網掛け用）
    non_working = []
    lo, hi = problem.to_min(start), problem.to_min(end)
    for rid in resource_ids:
        pr = problem.resources.get(rid)
        if pr is None:
            continue
        for s, e in gaps(pr.windows, problem.horizon):
            s, e = max(s, lo), min(e, hi)
            if e > s:
                non_working.append({"resource": rid, "start": _local(problem.to_dt(s), tz), "end": _local(problem.to_dt(e), tz)})

    # ---- 未割付タスク（ボードへドラッグして配置できる）
    unscheduled = [
        {
            "taskId": t.id, "orderId": t.order_id, "wbsNumber": problem.orders[t.order_id].no, "name": t.name,
            "durations": {str(o.resource_id): o.duration for o in t.options},
            "deadLine": _local(problem.to_dt(problem.orders[t.order_id].due), tz) if problem.orders[t.order_id].due is not None else None,
            "colorValue": (str(problem.orders[t.order_id].product_id) if problem.orders[t.order_id].product_id is not None
                           else problem.orders[t.order_id].no),
        }
        for t in problem.tasks.values() if t.id not in assigned
    ]

    # 既存DBの英語キーも日本語へ揃え、画面側の項目と一致させる。
    kpis = normalize_kpis({k.KpiKey: coerce(k.KpiValue) for k in db.scalars(select(PlanKpi).where(PlanKpi.PlanID == plan.PlanID))})
    return {
        "plan": {
            "planId": plan.PlanID, "planName": plan.PlanName, "status": plan.Status,
            "timeUnit": setting.TimeUnit if setting else "DAY",
            "startAt": _local(plan.StartAt, tz), "endAt": _local(plan.EndAt, tz),
            "rowVer": plan.RowVer,
        },
        "timeZone": tz,
        "from": _local(start, tz),
        "to": _local(end, tz),
        "groups": group_list,
        "resources": resources,
        "events": events,
        "setups": setups,
        "nonWorking": non_working,
        "unscheduled": unscheduled,
        "issues": [
            # 実際の承認処理と同じ判定結果を画面へ返す。
            {"severity": v.Severity, "message": v.Message, "taskId": v.TaskID,
             "blocksApproval": blocks_plan_approval(v, assigned)}
            for v in sorted(issues, key=lambda v: (SEVERITY_ORDER[v.Severity], v.ViolationID))
        ],
        "kpis": kpis,
    }

"""計画比較（KPI 差分と差異のあるタスク）と実績登録。"""
from datetime import date, datetime, time, timedelta

from fastapi import HTTPException
from sqlalchemy import false, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import chunks
from app.core.timeutil import to_jst_naive, as_jst
from app.engine.compare import Slot, assignment_diff, kpi_deltas
from app.models.masters import Product, Resource, ResourceGroup, Location, Worker
from app.models.transactions import Order, Plan, PlanAssignment, PlanKpi, Task
from app.schemas.base import coerce
from app.services.plan_lifecycle import master_assignments

KIND_LABEL = {"MOVED": "時刻変更", "RESOURCE": "設備変更", "ADDED": "追加", "REMOVED": "割付解除"}


# 日時を拠点の現地時刻へ変換して表示用の文字列にする。
def _hhmm(dt: datetime, tz: str) -> str:
    return as_jst(dt).strftime("%m/%d %H:%M")


# 割付の移動分数と設備・作業者変更から、比較結果の説明を組み立てる。
def _shift_text(kind: str, minutes: int | None, worker_mode: bool = False) -> str:
    if minutes is None or minutes == 0:
        if kind == "RESOURCE" and worker_mode:
            return "担当作業者変更"
        return KIND_LABEL[kind]
    if worker_mode and abs(minutes) % 1440 == 0:
        span = f"{abs(minutes) // 1440}日"
    else:
        h, m = divmod(abs(minutes), 60)
        span = f"{h}時間{m:02d}分" if h else f"{m}分"
    suffix = ("・担当変更" if worker_mode else "・設備変更") if kind == "RESOURCE" else ""
    return f"{span}{'後ろ倒し' if minutes > 0 else '前倒し'}{suffix}"


# 二つの計画の評価値と割付を比較し、画面表示用の差分を返す。
def compare_plans(db: Session, a_id: int, b_id: int) -> dict:
    plan_a, plan_b = db.get(Plan, a_id), db.get(Plan, b_id)
    if plan_a is None or plan_b is None:
        raise HTTPException(404, "計画が見つかりません")
    tz = get_settings().app_timezone

    # 指定した計画の評価値を項目名で引ける形にまとめる。
    def kpis(pid):
        return {k.KpiKey: coerce(k.KpiValue) for k in db.scalars(select(PlanKpi).where(PlanKpi.PlanID == pid))}

    # 指定した計画の割付をタスクごとにまとめる（日次モードはWorkerIDを割付先として比較する）。
    def slots(pid):
        rows = db.scalars(select(PlanAssignment).where(PlanAssignment.PlanID == pid)).all()
        return {
            a.TaskID: Slot(a.ResourceID if a.ResourceID is not None else a.WorkerID, a.StartAt, a.EndAt)
            for a in rows
        }, any(a.ResourceID is None and a.WorkerID is not None for a in rows)

    sa, a_day = slots(a_id)
    sb, b_day = slots(b_id)
    worker_mode = a_day or b_day
    changes = assignment_diff(sa, sb)
    task_ids = {c.task_id for c in changes}
    info = {
        t.TaskID: (j.WBSNumber, t.TaskName)
        for ids in chunks(task_ids)
        for t, j in db.execute(select(Task, Order).join(Order, Order.OrderID == Task.OrderID).where(Task.TaskID.in_(ids)))
    }
    res = {r.ResourceID: r for r in db.scalars(select(Resource).where(Resource.LocationID == plan_a.LocationID))}
    workers = {w.WorkerID: w for w in db.scalars(select(Worker).where(Worker.LocationID == plan_a.LocationID))}

    # 比較対象の割付を、設備名または作業者名と現地時刻の表示情報へ変換する。
    def slot_view(s: Slot | None):
        if s is None:
            return None
        if worker_mode:
            w = workers.get(s.resource_id) if s.resource_id is not None else None
            name = w.WorkerName if w else (str(s.resource_id) if s.resource_id is not None else "—")
            return {"resourceId": s.resource_id, "resourceName": name,
                    "start": as_jst(s.start).strftime("%m/%d"),
                    "end": as_jst(s.end - timedelta(seconds=1)).strftime("%m/%d") if s.end > s.start else as_jst(s.end).strftime("%m/%d")}
        r = res.get(s.resource_id) if s.resource_id is not None else None
        return {"resourceId": s.resource_id, "resourceName": r.ResourceName if r else (str(s.resource_id) if s.resource_id is not None else "—"),
                "start": _hhmm(s.start, tz), "end": _hhmm(s.end, tz)}

    # 比較対象の計画名・状態・期間を表示用にまとめる。
    def summary(p: Plan):
        return {"planId": p.PlanID, "planName": p.PlanName, "status": p.Status,
                "startAt": _hhmm(p.StartAt, tz), "endAt": _hhmm(p.EndAt, tz)}

    return {
        "a": summary(plan_a),
        "b": summary(plan_b),
        "kpis": [
            {"key": d.key, "label": d.label, "unit": d.unit, "a": d.a, "b": d.b, "delta": d.delta, "better": d.better}
            for d in kpi_deltas(kpis(a_id), kpis(b_id))
        ],
        "changedCount": len(changes),
        "totalTasks": len(set(sa) | set(sb)),
        "changes": [
            {
                "taskId": c.task_id, "wbsNumber": info.get(c.task_id, ("", ""))[0], "taskName": info.get(c.task_id, ("", ""))[1],
                "kind": c.kind, "shiftMinutes": c.shift_minutes, "description": _shift_text(c.kind, c.shift_minutes, worker_mode),
                "a": slot_view(c.a), "b": slot_view(c.b),
            }
            for c in changes
        ],
    }


# 指定日のマスタ計画の割付を、設備別・開始順の実績登録へまとめる。
def dispatch_list(db: Session, location_id: int, day: date, resource_group_id: int | None = None) -> dict:
    """マスタ計画の実績登録（指定日の現地 0:00〜24:00、リソース別・開始順）。"""
    # 対象の拠点情報。現地時刻や既定設定の参照に使う。
    location = db.get(Location, location_id)
    if location is None:
        raise HTTPException(404, f"拠点 {location_id} が見つかりません")
    tz = get_settings().app_timezone
    start = to_jst_naive(datetime.combine(day, time()))
    end = to_jst_naive(datetime.combine(day + timedelta(days=1), time()))
    rows = master_assignments(db, location_id, start, end)
    task_ids = [a.TaskID for a in rows]
    detail = {
        t.TaskID: (t, j, product)
        for ids in chunks(task_ids)
        for t, j, product in db.execute(
            select(Task, Order, Product).join(Order, Order.OrderID == Task.OrderID).outerjoin(Product, Product.ProductID == Order.ProductID)
            .where(Task.TaskID.in_(ids))
        )
    }
    groups = {g.ResourceGroupID: g for g in db.scalars(select(ResourceGroup).where(ResourceGroup.LocationID == location_id))}
    resources = [
        r for r in db.scalars(select(Resource).where(Resource.LocationID == location_id, Resource.DeleteFlag == false()))
        if resource_group_id is None or r.ResourceGroupID == resource_group_id
    ]
    resources.sort(key=lambda r: (groups[r.ResourceGroupID].SortOrder if r.ResourceGroupID in groups else 9999, r.SortOrder, r.ResourceName, r.ResourceID))
    out = []
    for r in resources:
        # このリソースの実績登録に表示する割付一覧。画面側のassignmentsと対応する。
        assignments = []
        for a in (x for x in rows if x.ResourceID == r.ResourceID):
            t, j, product = detail[a.TaskID]
            assignments.append({
                "assignmentId": a.AssignmentID, "taskId": t.TaskID, "wbsNumber": j.WBSNumber, "taskName": t.TaskName,
                "productName": product.ProductName if product else None,
                "quantity": coerce(j.Quantity),
                "start": as_jst(a.StartAt).strftime("%H:%M"),
                "end": as_jst(a.EndAt).strftime("%H:%M"),
                "startAt": as_jst(a.StartAt).isoformat(), "endAt": as_jst(a.EndAt).isoformat(),
                "setupMinutes": a.SetupMinutes, "isLocked": a.IsLocked, "taskStatus": t.Status,
            })
        out.append({
            "resourceId": r.ResourceID, "resourceName": r.ResourceName,
            "groupName": groups[r.ResourceGroupID].GroupName if r.ResourceGroupID in groups else None,
            "assignments": assignments,
        })
    return {"locationId": location_id, "date": day.isoformat(), "timeZone": tz, "resources": out}

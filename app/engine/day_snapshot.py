"""DBから日次バケット計算・検証・手動編集用の DayProblem を構築する。"""
from datetime import date, datetime, time, timedelta

from fastapi import HTTPException
from sqlalchemy import false, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import chunks
from app.engine.day_problem import (
    DayDependency,
    DayLock,
    DayOrder,
    DayProblem,
    DayTask,
    DayWorker,
    scale_qty,
)
from app.models.masters import (
    CalculationSetting,
    Location,
    Product,
    ProductProcess,
    Worker,
    WorkerCalendar,
    WorkerCalendarException,
    WorkerSkillMap,
)
from app.models.transactions import Order, Plan, PlanAssignment, Task
from app.services.calendar_service import calendar_specs
from app.services.task_conditions import TaskWeekdayRestriction
from app.services.product_validation import validate_weekday_settings
from app.services.worktime import ExceptionSpec, WorkSpec, expand_working_time

# 出荷日逆算・期間外ロックの変換に使う計画前後の稼働日展開バッファ（暦日）。
CALENDAR_BUFFER_DAYS = 90


# 週次勤務と停止例外を展開し、1分でも稼働時間が残る日付の集合を返す。
def _active_dates(
    work_rows: list[WorkSpec],
    exceptions: list[ExceptionSpec],
    first_day: date,
    last_day: date,
    tz: str,
) -> set[date]:
    if last_day < first_day:
        return set()
    # 勤務未登録の拠点は全暦日を稼働日として扱う。
    if not work_rows:
        out: set[date] = set()
        cur = first_day
        while cur <= last_day:
            out.add(cur)
            cur += timedelta(days=1)
        return out
    start_dt = datetime.combine(first_day, time(0, 0))
    end_dt = datetime.combine(last_day + timedelta(days=1), time(0, 0))
    intervals = expand_working_time(work_rows, exceptions, start_dt, end_dt, tz)
    return {s.date() for s, e in intervals if e > s}


# 指定日以前で最も近い稼働日の拡張インデックスを返す（非稼働日の出荷日対応）。
def _floor_working_idx(target: date, ext_dates: list[date], date_to_ext: dict[date, int]) -> int | None:
    if target in date_to_ext:
        return date_to_ext[target]
    best: int | None = None
    for d in ext_dates:
        if d <= target:
            best = date_to_ext[d]
        else:
            break
    return best


# 指定日以降で最も近い稼働日の拡張インデックスを返す（着手可能日対応）。
def _ceil_working_idx(target: date, ext_dates: list[date], date_to_ext: dict[date, int]) -> int:
    if target in date_to_ext:
        return date_to_ext[target]
    for d in ext_dates:
        if d >= target:
            return date_to_ext[d]
    return date_to_ext[ext_dates[-1]] + 1 if ext_dates else 0


# 計画の拠点に属する稼働日・作業者・オーダー・タスクを DayProblem へまとめる。
def build_day_problem(db: Session, plan: Plan, scope: str = "FULL") -> DayProblem:
    location = db.get(Location, plan.LocationID)
    setting = db.get(CalculationSetting, plan.CalculationSettingID)
    tz = get_settings().app_timezone
    start, end = plan.StartAt, plan.EndAt

    weights = dict(setting.ObjectiveWeightsJSON or {}) if setting else {}
    if scope == "REPAIR":
        weights.setdefault("stability", 20)

    # ---- 計画期間と前後バッファの稼働日軸を構築する
    plan_first = start.date()
    plan_last = (end - timedelta(seconds=1)).date() if end > start else plan_first
    buf_first = plan_first - timedelta(days=CALENDAR_BUFFER_DAYS)
    buf_last = plan_last + timedelta(days=CALENDAR_BUFFER_DAYS)

    loc_work, loc_excs = calendar_specs(db, location.LocationID)
    loc_active = _active_dates(loc_work, loc_excs, buf_first, buf_last, tz)
    ext_dates = sorted(loc_active)
    working_days = [d for d in ext_dates if plan_first <= d <= plan_last]

    # 計画期間内の先頭稼働日をインデックス0とし、前後の稼働日も連続整数で番号付けする。
    if working_days:
        origin_pos = ext_dates.index(working_days[0])
    else:
        origin_pos = next((i for i, d in enumerate(ext_dates) if d >= plan_first), len(ext_dates))
    date_to_ext: dict[date, int] = {}
    ext_to_date: dict[int, date] = {}
    for pos, d in enumerate(ext_dates):
        idx = pos - origin_pos
        date_to_ext[d] = idx
        ext_to_date[idx] = d

    # ---- 作業者と出勤可能日（半休は通常勤務が1分でも残れば出勤可能、全休のみ不在）
    worker_rows = db.scalars(
        select(Worker)
        .where(Worker.LocationID == location.LocationID, Worker.DeleteFlag == false())
        .order_by(Worker.WorkerID)
    ).all()
    worker_ids = [w.WorkerID for w in worker_rows]

    worker_cals: dict[int, list[WorkSpec]] = {wid: [] for wid in worker_ids}
    worker_excs: dict[int, list[ExceptionSpec]] = {wid: [] for wid in worker_ids}
    if worker_ids:
        for batch in chunks(worker_ids):
            for wc in db.scalars(
                select(WorkerCalendar).where(
                    WorkerCalendar.WorkerID.in_(batch), WorkerCalendar.DeleteFlag == false()
                )
            ):
                worker_cals[wc.WorkerID].append(WorkSpec(wc.DayOfWeek, wc.StartTime, wc.EndTime))
            for we in db.scalars(
                select(WorkerCalendarException).where(WorkerCalendarException.WorkerID.in_(batch))
            ):
                worker_excs[we.WorkerID].append(ExceptionSpec(we.StartAt, we.EndAt))

    workers: dict[int, DayWorker] = {}
    for w in worker_rows:
        # 作業者の通常勤務が未登録の場合は拠点カレンダーを既定として本人の例外休日だけ差し引く。
        w_work = worker_cals[w.WorkerID] if worker_cals[w.WorkerID] else loc_work
        combined_excs = loc_excs + worker_excs[w.WorkerID]
        w_active = _active_dates(w_work, combined_excs, plan_first, plan_last, tz)
        avail = {date_to_ext[d] for d in w_active if d in date_to_ext and 0 <= date_to_ext[d] < len(working_days)}
        max_qty = scale_qty(w.MaxDailyQuantity) if w.MaxDailyQuantity is not None else None
        workers[w.WorkerID] = DayWorker(id=w.WorkerID, name=w.WorkerName, max_daily_qty=max_qty, available_days=avail)

    # ---- オーダーと製品・工程・タスクの読み込み
    order_filter = (
        Order.LocationID == location.LocationID,
        Order.DeleteFlag == false(),
        Order.Status.notin_(["DONE", "CANCELLED"]),
        or_(Order.ReleaseAt.is_(None), Order.ReleaseAt < end),
    )
    order_rows = db.scalars(select(Order).where(*order_filter)).all()
    product_ids = {o.ProductID for o in order_rows if o.ProductID is not None}
    products: dict[int, Product] = {}
    processes: dict[int, ProductProcess] = {}
    by_product: dict[int, list[ProductProcess]] = {}
    for batch in chunks(product_ids):
        for p in db.scalars(select(Product).where(Product.ProductID.in_(batch))):
            products[p.ProductID] = p
        for pp in db.scalars(
            select(ProductProcess)
            .where(ProductProcess.ProductID.in_(batch))
            .order_by(ProductProcess.SequenceNumber, ProductProcess.ProductProcessID)
        ):
            processes[pp.ProductProcessID] = pp
            by_product.setdefault(pp.ProductID, []).append(pp)

    orders: dict[int, DayOrder] = {}
    order_release_idx: dict[int, int] = {}
    for o in order_rows:
        prod = products.get(o.ProductID) if o.ProductID is not None else None
        # 出荷日を優先し、未指定時は納期を出荷基準日として使う。
        ship_dt = o.ShippingDate or o.DeadLine
        ship_date = ship_dt.date() if ship_dt else None
        ship_idx = _floor_working_idx(ship_date, ext_dates, date_to_ext) if ship_date else None
        orders[o.OrderID] = DayOrder(
            id=o.OrderID,
            no=o.WBSNumber,
            name=o.OrderName,
            quantity_scaled=scale_qty(o.Quantity),
            exclude_from_daily_cap=bool(prod.ExcludeFromDailyCap) if prod else False,
            shipping_day_idx=ship_idx,
            shipping_date=ship_date,
            priority=o.Priority,
            product_id=o.ProductID,
            preferred_worker_ids=set(o.worker_ids),
        )
        if o.ReleaseAt is not None:
            order_release_idx[o.OrderID] = max(0, _ceil_working_idx(o.ReleaseAt.date(), ext_dates, date_to_ext))
        else:
            order_release_idx[o.OrderID] = 0

    task_filter = (
        Task.OrderID.in_(select(Order.OrderID).where(*order_filter)),
        Task.Status.notin_(["DONE", "CANCELLED"]),
    )
    task_rows = db.scalars(select(Task).where(*task_filter).order_by(Task.OrderID, Task.Sequence, Task.TaskID)).all()

    # 製品工程の未生成チェック（分単位モードと同じく不完全なタスク生成を事前に案内する）
    generated: dict[int, set[int]] = {}
    for batch in chunks(orders):
        for oid, ppid in db.execute(
            select(Task.OrderID, Task.ProductProcessID).where(
                Task.OrderID.in_(batch), Task.ProductProcessID.is_not(None)
            )
        ):
            generated.setdefault(oid, set()).add(ppid)
    missing_errors: list[str] = []
    for oid, dorder in orders.items():
        missing = [
            pp.ProcessName for pp in by_product.get(dorder.product_id, [])
            if pp.ProductProcessID not in generated.get(oid, set())
        ]
        if missing:
            missing_errors.append(
                f"{dorder.no}: 未生成の工程があります（{'、'.join(missing)}）。タスク生成を確認してください。"
            )
    if missing_errors:
        raise HTTPException(422, " ".join(missing_errors))

    # ---- スキルマップ（製品工程ごとの実行可能作業者）
    skill_workers: dict[int, list[int]] = {}
    if processes and worker_ids:
        for batch in chunks(processes):
            for sm in db.scalars(
                select(WorkerSkillMap).where(
                    WorkerSkillMap.ProductProcessID.in_(batch),
                    WorkerSkillMap.CanExecute == True,  # noqa: E712
                )
            ):
                if sm.WorkerID in workers:
                    skill_workers.setdefault(sm.ProductProcessID, []).append(sm.WorkerID)
    for ppid in skill_workers:
        skill_workers[ppid].sort()

    # ---- 前回の割付（自計画優先、なければ元計画）
    def assignments_of(plan_id: int | None) -> dict[int, PlanAssignment]:
        if plan_id is None:
            return {}
        return {a.TaskID: a for a in db.scalars(select(PlanAssignment).where(PlanAssignment.PlanID == plan_id))}

    own = assignments_of(plan.PlanID)
    base = assignments_of(plan.BasePlanID)
    frozen_hours = setting.FrozenWindowHours if setting else 0
    frozen_dt = start + timedelta(hours=frozen_hours)

    # ---- 各オーダー×各工程区分で最小SequenceNumber（日上限カウント対象の先頭工程）を特定する
    first_seq_by_order_group: dict[tuple[int, int], int] = {}
    for t in task_rows:
        pp = processes.get(t.ProductProcessID) if t.ProductProcessID is not None else None
        if pp is not None and pp.ProcessGroupID is not None:
            key = (t.OrderID, pp.ProcessGroupID)
            if key not in first_seq_by_order_group or pp.SequenceNumber < first_seq_by_order_group[key]:
                first_seq_by_order_group[key] = pp.SequenceNumber

    # ---- タスク構築
    tasks: dict[int, DayTask] = {}
    by_order_proc: dict[int, dict[int, Task]] = {}
    for t in task_rows:
        dorder = orders.get(t.OrderID)
        if dorder is None:
            continue
        pp = processes.get(t.ProductProcessID) if t.ProductProcessID is not None else None
        if pp is not None and pp.ProductID == dorder.product_id:
            by_order_proc.setdefault(t.OrderID, {})[pp.ProductProcessID] = t

        seq = pp.SequenceNumber if pp else t.Sequence
        pg_id = pp.ProcessGroupID if pp else None
        std_offset = pp.StandardOffsetDays if pp else None
        dur_days = max(1, int(pp.DurationDays or 1)) if pp else 1
        std_day_idx = (
            dorder.shipping_day_idx - std_offset
            if dorder.shipping_day_idx is not None and std_offset is not None
            else None
        )

        # 工程区分の先頭工程（または単独工程）かつ通常製品・数量>0のみ1日台数上限にカウントする。
        is_group_head = pg_id is None or first_seq_by_order_group.get((t.OrderID, pg_id)) == seq
        counts_cap = is_group_head and (not dorder.exclude_from_daily_cap) and (dorder.quantity_scaled > 0)

        # 実行可能作業者はスキルマップから抽出し、オーダー指定作業者と重なりがあればそこへ絞り込む。
        candidates = list(skill_workers.get(pp.ProductProcessID, [])) if pp else []
        if dorder.preferred_worker_ids and candidates:
            narrowed = [wid for wid in candidates if wid in dorder.preferred_worker_ids]
            if narrowed:
                candidates = narrowed

        # 曜日制限（既存TaskWeekdayRestrictionと同じ適用期間判定を共用する）
        allowed_weekdays: list[int] | None = None
        if pp is not None:
            validate_weekday_settings(pp, {})
            allowed_weekdays = TaskWeekdayRestriction(
                weekdays=list(pp.AllowedWeekdaysJSON),
                enabled=pp.WeekdayRestrictionEnabled,
                start_at=pp.WeekdayRestrictionStartAt,
                end_at=pp.WeekdayRestrictionEndAt,
            ).allowed_at(start)

        release_idx = order_release_idx.get(t.OrderID, 0)
        if t.EarliestStartAt is not None:
            release_idx = max(release_idx, _ceil_working_idx(t.EarliestStartAt.date(), ext_dates, date_to_ext))
        if frozen_hours > 0:
            release_idx = max(release_idx, _ceil_working_idx(frozen_dt.date(), ext_dates, date_to_ext))

        deadline_idx = (
            _floor_working_idx(t.DeadlineAt.date(), ext_dates, date_to_ext)
            if t.DeadlineAt is not None
            else None
        )

        dtask = DayTask(
            id=t.TaskID,
            order_id=t.OrderID,
            name=f"{dorder.no} {t.TaskName}",
            process_name=t.TaskName,
            product_process_id=t.ProductProcessID,
            sequence_number=seq,
            process_group_id=pg_id,
            counts_for_daily_cap=counts_cap,
            standard_offset_days=std_offset,
            standard_day_idx=std_day_idx,
            duration_days=dur_days,
            eligible_worker_ids=candidates,
            release_day_idx=release_idx,
            allowed_weekdays=allowed_weekdays,
            deadline_day_idx=deadline_idx,
        )

        # 前回割付（作業者が割り当てられているもの）からロック／ヒントを復元する。
        prev = own.get(t.TaskID) or base.get(t.TaskID)
        if prev is not None and prev.WorkerID is not None:
            s_idx = date_to_ext.get(prev.StartAt.date())
            end_d = (prev.EndAt - timedelta(seconds=1)).date() if prev.EndAt.time() == time(0, 0) else prev.EndAt.date()
            e_idx = date_to_ext.get(end_d)
            if s_idx is not None and e_idx is not None and e_idx >= s_idx:
                pos = DayLock(prev.WorkerID, s_idx, e_idx)
                frozen = prev is base.get(t.TaskID) and prev.StartAt < frozen_dt
                if prev.IsLocked or frozen:
                    dtask.lock = pos
                elif 0 <= s_idx < len(working_days):
                    dtask.hint = pos
        tasks[t.TaskID] = dtask

    # ---- 工程間の前後関係（MinLagDays / MaxLagDays）
    dependencies: list[DayDependency] = []
    for oid, mapped in sorted(by_order_proc.items()):
        ordered_procs = by_product.get(orders[oid].product_id, [])
        for prev_pp, next_pp in zip(ordered_procs, ordered_procs[1:]):
            pred_t = mapped.get(prev_pp.ProductProcessID)
            succ_t = mapped.get(next_pp.ProductProcessID)
            if pred_t is None or succ_t is None:
                continue
            dependencies.append(DayDependency(
                pred=pred_t.TaskID,
                succ=succ_t.TaskID,
                min_lag_days=max(0, int(prev_pp.MinLagDays or 0)),
                max_lag_days=int(prev_pp.MaxLagDays) if prev_pp.MaxLagDays is not None else None,
            ))

    return DayProblem(
        horizon_start=start,
        horizon_end=end,
        tz=tz,
        working_days=working_days,
        date_to_ext_idx=date_to_ext,
        ext_idx_to_date=ext_to_date,
        workers=workers,
        orders=orders,
        tasks=tasks,
        dependencies=dependencies,
        weights=weights,
    )

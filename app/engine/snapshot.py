"""計算に必要なデータをすべて DB から読み込み `Problem` を作る。

対象:
  * 計画の拠点のリソース（未削除）と、そのカレンダー（なければ拠点の既定
    カレンダー）から求めた稼働枠
  * 拠点のオーダーのうち DONE / CANCELLED 以外、スケジューラ管理、計画期間終了前に
    着手可能なもの。その非集約・未完了タスク
  * リソース候補（グループ指定は所属リソースごとに展開）
  * 対象タスク間の依存関係
  * ロック: この計画と元計画のロック済み割付、および確定期間内に始まる元計画の作業
  * ヒント: それ以外のこの計画（または元計画）の割付。初期解として使う
  * 拠点の有効な段取り替えマトリクスとルール
"""
from sqlalchemy import false, or_, select, true
from sqlalchemy.orm import Session

from app.core.timeutil import utc_to_local
from app.engine.problem import (
    PChangeover,
    PDependency,
    POrder,
    PLock,
    POption,
    PResource,
    Problem,
    PRule,
    PTask,
)
from app.models.masters import ChangeoverMatrix, PlanProfile, Resource, Rule, Location
from app.models.transactions import Order, Plan, PlanAssignment, Task, TaskDependency
from app.services.calendar_service import working_time
from app.services.worktime import Interval


# 稼働時間の区間を、計画開始からの分数と計画期間内の範囲へ変換する。
def _windows(intervals: list[Interval], problem_start, horizon: int) -> list[tuple[int, int]]:
    out = []
    for s, e in intervals:
        a = int((s - problem_start).total_seconds() // 60)
        b = int((e - problem_start).total_seconds() // 60)
        a, b = max(0, a), min(horizon, b)
        if b > a:
            out.append((a, b))
    return out


# 計画の拠点に属する作業・設備・カレンダー・ルールを計算条件へまとめる。
def build_problem(db: Session, plan: Plan, scope: str = "FULL") -> Problem:
    # 対象の拠点情報。現地時刻や既定設定の参照に使う。
    location = db.get(Location, plan.LocationID)
    profile = db.get(PlanProfile, plan.ProfileID)
    tz = location.TimeZone
    start, end = plan.HorizonStart, plan.HorizonEnd
    horizon = int((end - start).total_seconds() // 60)
    to_min = lambda dt: int((dt - start).total_seconds() // 60)  # noqa: E731

    weights = dict(profile.ObjectiveWeightsJSON or {}) if profile else {}
    if scope == "REPAIR":
        weights.setdefault("stability", 20)

    # ---- リソースとカレンダー
    resources: dict[int, PResource] = {}
    rows = db.scalars(
        select(Resource).where(Resource.LocationID == location.LocationID, Resource.DeleteFlag == false())
    ).all()
    calendar_cache: dict[int, list[tuple[int, int]]] = {}
    for r in rows:
        cal_id = r.CalendarID or location.DefaultCalendarID
        if cal_id is None:
            windows = [(0, horizon)]  # カレンダーなし: 常に稼働
        else:
            if cal_id not in calendar_cache:
                calendar_cache[cal_id] = _windows(working_time(db, cal_id, start, end, tz), start, horizon)
            windows = calendar_cache[cal_id]
        resources[r.ResourceID] = PResource(
            id=r.ResourceID, code=r.ResourceCode, name=r.ResourceName,
            capacity=max(1, int(r.Capacity or 1)), windows=windows, group_id=r.ResourceGroupID,
        )
    members: dict[int, list[int]] = {}
    for r in rows:
        if r.ResourceGroupID:
            members.setdefault(r.ResourceGroupID, []).append(r.ResourceID)

    # ---- オーダーとタスク
    order_filter = (
        Order.LocationID == location.LocationID,
        Order.DeleteFlag == false(),
        Order.Status.notin_(["DONE", "CANCELLED"]),
        Order.PlanOwner == "SCHEDULER",
        or_(Order.ReleaseAt.is_(None), Order.ReleaseAt < end),
    )
    orders_rows = db.scalars(select(Order).where(*order_filter)).all()
    orders = {
        j.OrderID: POrder(id=j.OrderID, no=j.OrderNo, due=to_min(j.DueAt) if j.DueAt else None, priority=j.Priority)
        for j in orders_rows
    }
    order_release = {j.OrderID: max(0, to_min(j.ReleaseAt)) if j.ReleaseAt else 0 for j in orders_rows}
    # IN 句は値のリストではなくサブクエリにする（SQL Server のパラメータ上限 2,100 を超えないように）
    task_filter = (
        Task.OrderID.in_(select(Order.OrderID).where(*order_filter)),
        Task.IsSummary == false(),
        Task.Status.notin_(["DONE", "CANCELLED"]),
    )
    task_rows = db.scalars(select(Task).where(*task_filter)).all()

    # ---- 前回の位置: この計画を優先し、なければ元計画
    def assignments_of(plan_id: int | None) -> dict[int, PlanAssignment]:
        if plan_id is None:
            return {}
        return {a.TaskID: a for a in db.scalars(select(PlanAssignment).where(PlanAssignment.PlanID == plan_id))}

    own = assignments_of(plan.PlanID)
    base = assignments_of(plan.BasePlanID)
    frozen_end = (profile.FrozenWindowHours if profile else 0) * 60

    tasks: dict[int, PTask] = {}
    for t in task_rows:
        options: list[POption] = []
        for o in t.options:
            targets = [o.ResourceID] if o.ResourceID else members.get(o.ResourceGroupID, [])
            options.extend(POption(rid, int(o.DurationMin), int(o.Priority or 1)) for rid in targets if rid in resources)
        release = order_release.get(t.OrderID, 0)
        if t.EarliestStartAt:
            release = max(release, to_min(t.EarliestStartAt))
        release = max(release, frozen_end)  # 確定期間内には新しい作業を開始しない
        task = PTask(
            id=t.TaskID, order_id=t.OrderID, name=f"{orders[t.OrderID].no} {t.TaskName}",
            attrs=dict(t.AttributesJSON or {}), options=options, release=release,
            deadline=to_min(t.DeadlineAt) if t.DeadlineAt else None,
        )
        prev = own.get(t.TaskID) or base.get(t.TaskID)
        if prev is not None:
            pos = PLock(prev.ResourceID, to_min(prev.StartAt), to_min(prev.EndAt))
            frozen = prev is base.get(t.TaskID) and pos.start < frozen_end
            if (prev.IsLocked or frozen) and pos.end > 0 and pos.end > pos.start:
                task.lock = pos
            elif 0 <= pos.start < horizon:
                task.hint = pos
        tasks[t.TaskID] = task

    deps = [
        PDependency(d.PredecessorTaskID, d.SuccessorTaskID, d.DependencyType, int(d.LagMin or 0),
                    int(d.MaxLagMin) if d.MaxLagMin is not None else None)
        for d in db.scalars(
            select(TaskDependency).where(TaskDependency.SuccessorTaskID.in_(select(Task.TaskID).where(*task_filter)))
        )
        if d.PredecessorTaskID in tasks
    ]

    # ---- 段取り替えとルール
    changeovers = []
    for mx in db.scalars(
        select(ChangeoverMatrix).where(ChangeoverMatrix.LocationID == location.LocationID, ChangeoverMatrix.IsActive == true())
    ):
        rids = set(members.get(mx.ResourceGroupID, [])) if mx.ResourceGroupID else set(resources)
        changeovers.append(PChangeover(
            id=mx.MatrixID, attribute=mx.AttributeKey, resource_ids=rids, default=int(mx.DefaultMinutes or 0),
            entries={(e.FromValue, e.ToValue): (int(e.SetupMinutes or 0), bool(e.IsForbidden)) for e in mx.entries},
        ))
    plan_day = utc_to_local(start, tz).date()  # ルールの有効期間は現地の開始日で判定する
    rules = [
        PRule(r.RuleID, r.RuleTypeKey, r.RuleName, dict(r.SelectorJSON or {}), dict(r.ParamsJSON or {}),
              bool(r.IsHard), int(r.Weight or 100))
        for r in db.scalars(select(Rule).where(Rule.LocationID == location.LocationID, Rule.IsActive == true()))
        if (r.ValidFrom is None or r.ValidFrom <= plan_day) and (r.ValidTo is None or r.ValidTo >= plan_day)
    ]

    return Problem(
        horizon_start=start, horizon=horizon, tz=tz, resources=resources, tasks=tasks, orders=orders,
        dependencies=deps, changeovers=changeovers, rules=rules, weights=weights,
        time_limit_sec=profile.TimeLimitSec if profile else 60,
    )

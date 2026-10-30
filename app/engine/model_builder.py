"""Problem -> CP-SAT モデルの構築と求解。

モデル（時刻はすべて計画期間開始からの整数分）:
  * 各タスク: 開始・終了、`scheduled` フラグ、対象リソースごとの任意区間。
    割付する場合はちょうど 1 つを選ぶ
  * リソース: 重なり禁止（能力 1）または累積制約（能力 > 1）。非稼働時間は
    固定のブロック区間として追加するため、タスクは 1 つの稼働枠内で実行される
  * 依存関係 FS/SS/FF/SF（最小・最大ラグ付き）
  * 段取り替え: リソースごとに AddCircuit を使用。アーク i→j は
    end_i + setup(i,j) <= start_j を課す。禁止の組合せにはアークを張らない
  * ロック済みタスクは位置を固定
  * 目的関数: 納期遅れ（オーダー優先度で重み付け）、未割付タスク、段取り時間合計、
    最終完了時刻、前回計画からの変動（安定性）
  * ルールプラグインが独自の制約を追加する（app.engine.rules）
"""
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ortools.sat.python import cp_model

from app.engine.problem import PChangeover, Problem, PTask
from app.engine.result import SAssignment
from app.engine.rules import get_plugin
from app.services.worktime import gaps, subtract

DEFAULT_WEIGHTS = {"lateness": 1000, "unscheduled": 100000, "setup": 10, "makespan": 1, "stability": 0}
MAX_CIRCUIT_NODES = 80  # これを超えるとそのリソースの順序依存段取りは無視する


@dataclass
class OptVar:
    resource_id: int
    duration: int
    presence: Any  # BoolVar
    interval: Any  # IntervalVar


@dataclass
class TaskVars:
    task: PTask
    start: Any
    end: Any
    scheduled: Any
    interval: Any  # タスク単位の任意区間（リソースを問わない）
    options: list[OptVar] = field(default_factory=list)


@dataclass
class BuildContext:
    problem: Problem
    model: cp_model.CpModel
    task_vars: dict[int, TaskVars] = field(default_factory=dict)
    objective: list[tuple[Any, int]] = field(default_factory=list)  # (式, 係数)
    # (リテラル, 前タスク, 後タスク, リソースID, 段取り分)
    setup_arcs: list[tuple[Any, int, int, int, int]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def add_penalty(self, expr: Any, coefficient: int) -> None:
        if coefficient:
            self.objective.append((expr, int(coefficient)))

    def weight(self, key: str) -> int:
        return int(self.problem.weights.get(key, DEFAULT_WEIGHTS.get(key, 0)))


def priority_factor(priority: int) -> int:
    """納期遅れの倍率×10: 優先度 1 → 49（4.9倍）、50 → 30、100 → 10。"""
    p = max(1, min(int(priority or 50), 100))
    return 10 + (100 - p) * 10 // 25


def _add_tasks(ctx: BuildContext) -> None:
    m, p, H = ctx.model, ctx.problem, ctx.problem.horizon
    for t in p.tasks.values():
        if t.lock is not None:
            lk = t.lock
            s = m.NewIntVar(lk.start, lk.start, f"s{t.id}")
            e = m.NewIntVar(lk.end, lk.end, f"e{t.id}")
            sched = m.NewBoolVar(f"sch{t.id}")
            m.Add(sched == 1)
            iv = m.NewIntervalVar(s, lk.end - lk.start, e, f"iv{t.id}")
            opt = OptVar(lk.resource_id, lk.end - lk.start, sched, iv)
            ctx.task_vars[t.id] = TaskVars(t, s, e, sched, iv, [opt])
            continue
        s = m.NewIntVar(min(t.release, H), H, f"s{t.id}")
        e = m.NewIntVar(0, H, f"e{t.id}")
        sched = m.NewBoolVar(f"sch{t.id}")
        size = m.NewIntVar(0, H, f"sz{t.id}")
        iv = m.NewOptionalIntervalVar(s, size, e, sched, f"iv{t.id}")
        tv = TaskVars(t, s, e, sched, iv)
        for o in t.options:
            if o.resource_id not in p.resources or o.duration <= 0 or o.duration > H:
                continue
            pres = m.NewBoolVar(f"p{t.id}_{o.resource_id}")
            oiv = m.NewOptionalIntervalVar(s, o.duration, e, pres, f"iv{t.id}_{o.resource_id}")
            tv.options.append(OptVar(o.resource_id, o.duration, pres, oiv))
        if tv.options:
            m.Add(sum(ov.presence for ov in tv.options) == sched)
        else:
            m.Add(sched == 0)
            ctx.notes.append(f"task {t.id}: no usable resource option")
        if t.hint is not None:
            m.AddHint(s, t.hint.start)
            m.AddHint(sched, 1)
            for ov in tv.options:
                m.AddHint(ov.presence, 1 if ov.resource_id == t.hint.resource_id else 0)
        ctx.task_vars[t.id] = tv


def _add_resources(ctx: BuildContext) -> None:
    m, p = ctx.model, ctx.problem
    for r in p.resources.values():
        ivs = [ov.interval for tv in ctx.task_vars.values() for ov in tv.options if ov.resource_id == r.id]
        if not ivs:
            continue
        # ロック済みのタスクは、計画者が非稼働時間に置いた場合でもそのまま受け入れる
        locked = [(tv.task.lock.start, tv.task.lock.end) for tv in ctx.task_vars.values()
                  if tv.task.lock is not None and tv.task.lock.resource_id == r.id]
        blocked = subtract(gaps(r.windows, p.horizon), locked) if locked else gaps(r.windows, p.horizon)
        blocks = [m.NewIntervalVar(s, e - s, e, f"gap{r.id}_{s}") for s, e in blocked]
        if r.capacity <= 1:
            m.AddNoOverlap(ivs + blocks)
        else:
            m.AddCumulative(ivs + blocks, [1] * len(ivs) + [r.capacity] * len(blocks), r.capacity)


def _changeover_for(problem: Problem, resource_id: int) -> PChangeover | None:
    return next((c for c in problem.changeovers if resource_id in c.resource_ids), None)


def _add_changeovers(ctx: BuildContext) -> None:
    m, p = ctx.model, ctx.problem
    for r in p.resources.values():
        co = _changeover_for(p, r.id)
        if co is None or r.capacity != 1:
            continue
        nodes = [(tv, ov) for tv in ctx.task_vars.values() for ov in tv.options if ov.resource_id == r.id]
        if not nodes:
            continue
        if len(nodes) > MAX_CIRCUIT_NODES:
            ctx.notes.append(f"resource {r.code}: {len(nodes)} candidate tasks, changeovers ignored")
            continue
        arcs = []
        for i, (_, ov) in enumerate(nodes, start=1):
            arcs.append((0, i, m.NewBoolVar(f"first{r.id}_{i}")))
            arcs.append((i, 0, m.NewBoolVar(f"last{r.id}_{i}")))
            arcs.append((i, i, ov.presence.Not()))
        for i, (tva, _) in enumerate(nodes, start=1):
            for j, (tvb, _) in enumerate(nodes, start=1):
                if i == j:
                    continue
                va, vb = tva.task.attrs.get(co.attribute), tvb.task.attrs.get(co.attribute)
                need, forbidden = co.lookup(va, vb) if va is not None and vb is not None else (0, False)
                if forbidden:
                    continue
                lit = m.NewBoolVar(f"arc{r.id}_{i}_{j}")
                arcs.append((i, j, lit))
                m.Add(tvb.start >= tva.end + need).OnlyEnforceIf(lit)
                if need:
                    ctx.setup_arcs.append((lit, tva.task.id, tvb.task.id, r.id, need))
        empty = m.NewBoolVar(f"empty{r.id}")
        arcs.append((0, 0, empty))
        presences = [ov.presence for _, ov in nodes]
        m.Add(sum(presences) == 0).OnlyEnforceIf(empty)
        m.Add(sum(presences) >= 1).OnlyEnforceIf(empty.Not())
        m.AddCircuit(arcs)
    setup_w = ctx.weight("setup")
    for lit, _, _, _, need in ctx.setup_arcs:
        ctx.add_penalty(lit, setup_w * need)


def _add_dependencies(ctx: BuildContext) -> None:
    m = ctx.model
    for d in ctx.problem.dependencies:
        a, b = ctx.task_vars.get(d.pred), ctx.task_vars.get(d.succ)
        if a is None or b is None:
            continue
        m.AddImplication(b.scheduled, a.scheduled)
        pred_ref, succ_ref = {
            "FS": (a.end, b.start), "SS": (a.start, b.start),
            "FF": (a.end, b.end), "SF": (a.start, b.end),
        }[d.type]
        both = [a.scheduled, b.scheduled]
        m.Add(succ_ref >= pred_ref + d.lag).OnlyEnforceIf(both)
        if d.max_lag is not None:
            m.Add(succ_ref <= pred_ref + d.max_lag).OnlyEnforceIf(both)


def _add_objective(ctx: BuildContext) -> None:
    m, p, H = ctx.model, ctx.problem, ctx.problem.horizon
    # 元計画からコピーしたロックタスクは、この計画期間の終了後に終わる場合がある
    HM = max([H] + [t.lock.end for t in p.tasks.values() if t.lock is not None])
    late_w, unsched_w = ctx.weight("lateness"), ctx.weight("unscheduled")
    by_order: dict[int, list[TaskVars]] = {}
    for tv in ctx.task_vars.values():
        by_order.setdefault(tv.task.order_id, []).append(tv)
        ctx.add_penalty(1 - tv.scheduled, unsched_w)

    for order_id, tvs in by_order.items():
        order = p.orders.get(order_id)
        if order is None or order.due is None:
            continue
        order_end = m.NewIntVar(0, HM, f"jend{order_id}")
        for tv in tvs:
            m.Add(order_end >= tv.end).OnlyEnforceIf(tv.scheduled)
            # 未割付のタスクは計画期間の終了時に完了したものとみなす。
            # これにより、タスクを外す方が遅れて行うより安くなることはない。
            m.Add(order_end >= H).OnlyEnforceIf(tv.scheduled.Not())
        late = m.NewIntVar(0, HM + abs(order.due), f"late{order_id}")
        m.Add(late >= order_end - order.due)
        ctx.add_penalty(late, late_w * priority_factor(order.priority) // 10)

    for tv in ctx.task_vars.values():
        if tv.task.deadline is not None:
            tl = m.NewIntVar(0, HM + abs(tv.task.deadline), f"tlate{tv.task.id}")
            m.Add(tl >= tv.end - tv.task.deadline).OnlyEnforceIf(tv.scheduled)
            ctx.add_penalty(tl, late_w)

    mk_w = ctx.weight("makespan")
    if mk_w:
        mk = m.NewIntVar(0, HM, "makespan")
        for tv in ctx.task_vars.values():
            m.Add(mk >= tv.end).OnlyEnforceIf(tv.scheduled)
        ctx.add_penalty(mk, mk_w)

    stab_w = ctx.weight("stability")
    if stab_w:
        for tv in ctx.task_vars.values():
            h = tv.task.hint
            if h is None or tv.task.lock is not None:
                continue
            dev = m.NewIntVar(0, HM + H, f"dev{tv.task.id}")
            m.Add(dev >= tv.start - h.start).OnlyEnforceIf(tv.scheduled)
            m.Add(dev >= h.start - tv.start).OnlyEnforceIf(tv.scheduled)
            ctx.add_penalty(dev, stab_w)
            for ov in tv.options:
                if ov.resource_id == h.resource_id:
                    ctx.add_penalty(1 - ov.presence, stab_w * 60)  # 設備の変更は約 1 時間のずれとみなす

    if ctx.objective:
        m.Minimize(sum(coef * expr for expr, coef in ctx.objective))


def build_model(problem: Problem) -> BuildContext:
    ctx = BuildContext(problem=problem, model=cp_model.CpModel())
    _add_tasks(ctx)
    _add_resources(ctx)
    _add_changeovers(ctx)
    _add_dependencies(ctx)
    for rule in problem.rules:
        plugin = get_plugin(rule.type_key)
        if plugin is None:
            ctx.notes.append(f"rule {rule.id}: unknown type '{rule.type_key}' ignored")
            continue
        plugin.apply(ctx, rule)
    _add_objective(ctx)
    return ctx


# ---------------------------------------------------------------- 求解
@dataclass
class SolveResult:
    status: str  # OPTIMAL / FEASIBLE / INFEASIBLE / MODEL_INVALID / UNKNOWN
    objective: float | None
    bound: float | None
    wall_time: float
    assignments: list[SAssignment]
    notes: list[str]


class _Progress(cp_model.CpSolverSolutionCallback):
    def __init__(self, on_progress: Callable[[dict], None] | None, should_stop: Callable[[], bool] | None):
        super().__init__()
        self.on_progress, self.should_stop, self.count = on_progress, should_stop, 0

    def on_solution_callback(self) -> None:
        self.count += 1
        if self.on_progress:
            try:
                self.on_progress({
                    "solutions": self.count,
                    "objective": self.ObjectiveValue(),
                    "bound": self.BestObjectiveBound(),
                    "wallTime": round(self.WallTime(), 2),
                })
            except Exception:  # 進捗報告の失敗で計算を止めてはならない
                pass
        if self.should_stop and self.should_stop():
            self.StopSearch()


def solve_problem(
    problem: Problem,
    time_limit_sec: float | None = None,
    workers: int = 8,
    on_progress: Callable[[dict], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> SolveResult:
    ctx = build_model(problem)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(time_limit_sec or problem.time_limit_sec)
    solver.parameters.num_workers = workers
    status = solver.Solve(ctx.model, _Progress(on_progress, should_stop))
    name = solver.StatusName(status)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return SolveResult(name, None, None, solver.WallTime(), [], ctx.notes)

    setup_into: dict[int, int] = {}
    for lit, _, to_task, _, need in ctx.setup_arcs:
        if solver.BooleanValue(lit):
            setup_into[to_task] = need
    out: list[SAssignment] = []
    for tv in ctx.task_vars.values():
        if not solver.BooleanValue(tv.scheduled):
            continue
        chosen = next(ov for ov in tv.options if solver.BooleanValue(ov.presence))
        out.append(SAssignment(
            task_id=tv.task.id,
            resource_id=chosen.resource_id,
            start=solver.Value(tv.start),
            end=solver.Value(tv.end),
            setup=setup_into.get(tv.task.id, 0),
            locked=tv.task.lock is not None,
        ))
    return SolveResult(name, solver.ObjectiveValue(), solver.BestObjectiveBound(), solver.WallTime(), out, ctx.notes)

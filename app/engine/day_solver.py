"""日次バケット方式の CP-SAT ソルバー。

制約:
  * 各タスクは計画期間内の稼働日（0 .. num_days - 1）と担当作業者を1組選ぶ
  * 作業者の出勤可能日（全休除外・半休は出勤扱い）と工程の許可曜日を守る
  * 同一オーダー×同一工程区分のタスクは同一作業者へ割り当てる
  * 同一オーダーの隣接工程は MinLagDays / MaxLagDays の稼働日間隔を守る
  * 作業者×稼働日ごとの1日作業台数上限（工程区分先頭工程のみカウント、部品分譲除外）を守る
  * リソース候補がある工程は候補リソースを1つ割り当て、リソースの1日稼働上限数量・同時作業数を守る
  * ロック済みタスクは位置・作業者・リソースを固定する
目的関数:
  * 未割付の最小化 ＞ 出荷日超過（出荷日−1稼働日超）の最小化 ＞
    標準日からの後ろ倒し（重）＞ 標準日からの前倒し（軽）＞ 安定性
"""
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from threading import Event, Thread
from typing import Any

from ortools.sat.python import cp_model

from app.core.timeutil import weekday_number
from app.engine.cancellation import watch_cancellation
from app.engine.day_problem import DayProblem, DayTask
from app.engine.model_builder import SolveResult, _Progress, priority_factor
from app.engine.result import SAssignment

# 日次バケット方式の既定評価重み（前倒し優先・後ろ倒しは出荷日−1稼働日まで許容）。
DAY_DEFAULT_WEIGHTS = {
    "unscheduled": 10_000_000,
    "lateness": 1_000_000,
    "late_shift": 300,
    "early_shift": 100,
    "makespan": 1,
    "stability": 0,
}


@dataclass
class _DayTaskVars:
    task: DayTask
    scheduled: Any  # BoolVar
    start_day: Any  # IntVar
    end_day: Any  # IntVar
    # worker_id -> BoolVar
    worker_vars: dict[int, Any] = field(default_factory=dict)
    # (worker_id, start_day_idx) -> BoolVar
    slot_vars: dict[tuple[int, int], Any] = field(default_factory=dict)
    # resource_id -> BoolVar（リソース必須工程のみ作成）
    resource_vars: dict[int, Any] = field(default_factory=dict)


@dataclass
class _DayBuildContext:
    problem: DayProblem
    model: cp_model.CpModel
    task_vars: dict[int, _DayTaskVars] = field(default_factory=dict)
    objective: list[tuple[Any, int]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def add_penalty(self, expr: Any, coefficient: int) -> None:
        if coefficient:
            self.objective.append((expr, int(coefficient)))

    def weight(self, key: str) -> int:
        # 分モード向けの未割付・納期遅れ重みが小さい場合でも、日次モードの階層が崩れない下限を保つ。
        raw = self.problem.weights.get(key)
        if raw is None:
            return DAY_DEFAULT_WEIGHTS.get(key, 0)
        return int(raw)


# タスクを指定作業者・開始稼働日で実行できるか判定する（出勤日・許可曜日・連休前制限・計画期間内）。
def _slot_allowed(problem: DayProblem, task: DayTask, worker_id: int, start_day: int) -> bool:
    worker = problem.workers.get(worker_id)
    if worker is None:
        return False
    end_day = start_day + task.duration_days - 1
    if start_day < task.release_day_idx or start_day < 0 or end_day >= problem.num_days:
        return False
    allowed_wd = set(task.allowed_weekdays) if task.allowed_weekdays is not None else None
    for d in range(start_day, end_day + 1):
        if d not in worker.available_days:
            return False
        if allowed_wd is not None and weekday_number(problem.working_days[d]) not in allowed_wd:
            return False
    # 工程終了直後に続く連休日数（拠点休日＋担当作業者の休み）が許容上限を超える配置を禁止する。
    if task.max_holidays_after is not None:
        holidays = problem.worker_holidays_after(worker_id, end_day)
        if holidays is not None and holidays > task.max_holidays_after:
            return False
    return True


# 各タスクの割付変数（稼働日×作業者）を作成する。
def _add_tasks(ctx: _DayBuildContext) -> None:
    m, p = ctx.model, ctx.problem
    num_days = p.num_days
    for task in p.tasks.values():
        if task.lock is not None:
            lk = task.lock
            sched = m.NewBoolVar(f"dsch_{task.id}")
            m.Add(sched == 1)
            s_day = m.NewIntVar(lk.start_day, lk.start_day, f"ds_{task.id}")
            e_day = m.NewIntVar(lk.end_day, lk.end_day, f"de_{task.id}")
            tv = _DayTaskVars(task=task, scheduled=sched, start_day=s_day, end_day=e_day)
            w_var = m.NewBoolVar(f"dw_{task.id}_{lk.worker_id}")
            m.Add(w_var == 1)
            tv.worker_vars[lk.worker_id] = w_var
            slot_var = m.NewBoolVar(f"dx_{task.id}_{lk.worker_id}_{lk.start_day}")
            m.Add(slot_var == 1)
            tv.slot_vars[(lk.worker_id, lk.start_day)] = slot_var
            if lk.resource_id is not None:
                r_var = m.NewBoolVar(f"dr_{task.id}_{lk.resource_id}")
                m.Add(r_var == 1)
                tv.resource_vars[lk.resource_id] = r_var
            ctx.task_vars[task.id] = tv
            continue

        sched = m.NewBoolVar(f"dsch_{task.id}")
        max_day = max(0, num_days - 1)
        s_day = m.NewIntVar(0, max_day, f"ds_{task.id}")
        e_day = m.NewIntVar(0, max_day + task.duration_days, f"de_{task.id}")
        tv = _DayTaskVars(task=task, scheduled=sched, start_day=s_day, end_day=e_day)

        # 実行可能な (作業者, 開始稼働日) の組合せだけ変数化してモデルを軽量に保つ。
        by_worker: dict[int, list[Any]] = defaultdict(list)
        all_slots: list[tuple[int, Any]] = []
        for wid in task.eligible_worker_ids:
            for d in range(task.release_day_idx, num_days - task.duration_days + 1):
                if not _slot_allowed(p, task, wid, d):
                    continue
                x = m.NewBoolVar(f"dx_{task.id}_{wid}_{d}")
                tv.slot_vars[(wid, d)] = x
                by_worker[wid].append(x)
                all_slots.append((d, x))

        resource_ready = (not task.requires_resource) or bool(task.eligible_resource_ids)
        if all_slots and resource_ready:
            m.Add(sum(x for _, x in all_slots) == sched)
            # 開始日と終了日を割付スロットと厳密に結び付ける。
            m.Add(s_day == sum(d * x for d, x in all_slots)).OnlyEnforceIf(sched)
            m.Add(e_day == s_day + (task.duration_days - 1)).OnlyEnforceIf(sched)
            for wid, xs in by_worker.items():
                w_var = m.NewBoolVar(f"dw_{task.id}_{wid}")
                m.Add(w_var == sum(xs))
                tv.worker_vars[wid] = w_var
            # リソース候補が登録された工程は、割付時に候補リソースからちょうど1つを選ぶ。
            if task.requires_resource:
                for rid in task.eligible_resource_ids:
                    r_var = m.NewBoolVar(f"dr_{task.id}_{rid}")
                    tv.resource_vars[rid] = r_var
                m.Add(sum(tv.resource_vars.values()) == sched)
        else:
            m.Add(sched == 0)
            if not all_slots:
                ctx.notes.append(f"task {task.id}: no usable worker/day slot")
            else:
                ctx.notes.append(f"task {task.id}: no usable resource")

        # 前回計画の位置があれば初期解ヒントとして与える。
        if task.hint is not None and (task.hint.worker_id, task.hint.start_day) in tv.slot_vars:
            m.AddHint(sched, 1)
            m.AddHint(s_day, task.hint.start_day)
            for key, x in tv.slot_vars.items():
                m.AddHint(x, 1 if key == (task.hint.worker_id, task.hint.start_day) else 0)
            if task.hint.resource_id is not None and task.hint.resource_id in tv.resource_vars:
                for rid, rv in tv.resource_vars.items():
                    m.AddHint(rv, 1 if rid == task.hint.resource_id else 0)

        ctx.task_vars[task.id] = tv


# 同一オーダー×同一工程区分のタスクは同一作業者へ割り当てる制約を追加する。
def _add_same_worker_constraints(ctx: _DayBuildContext) -> None:
    m, p = ctx.model, ctx.problem
    grouped: dict[tuple[int, int], list[_DayTaskVars]] = defaultdict(list)
    for tv in ctx.task_vars.values():
        if tv.task.process_group_id is not None:
            grouped[(tv.task.order_id, tv.task.process_group_id)].append(tv)

    for tvs in grouped.values():
        if len(tvs) < 2:
            continue
        tvs.sort(key=lambda item: (item.task.sequence_number, item.task.id))
        for prev_tv, next_tv in zip(tvs, tvs[1:]):
            # 両方がロック済みの場合は既存の手動固定を尊重して求解不能を防ぐ。
            if prev_tv.task.lock is not None and next_tv.task.lock is not None:
                continue
            both = [prev_tv.scheduled, next_tv.scheduled]
            all_wids = set(prev_tv.worker_vars) | set(next_tv.worker_vars)
            for wid in all_wids:
                a_var = prev_tv.worker_vars.get(wid)
                b_var = next_tv.worker_vars.get(wid)
                if a_var is not None and b_var is not None:
                    m.Add(a_var == b_var).OnlyEnforceIf(both)
                elif a_var is not None:
                    m.Add(a_var == 0).OnlyEnforceIf(both)
                elif b_var is not None:
                    m.Add(b_var == 0).OnlyEnforceIf(both)


# 同一オーダーの隣接工程について、最小・最大稼働日間隔制約を追加する。
def _add_dependencies(ctx: _DayBuildContext) -> None:
    m = ctx.model
    for dep in ctx.problem.dependencies:
        a = ctx.task_vars.get(dep.pred)
        b = ctx.task_vars.get(dep.succ)
        if a is None or b is None:
            continue
        # 両方がロック済みの場合は手動固定を受け入れ、違反は評価処理で検出する。
        if a.task.lock is not None and b.task.lock is not None:
            continue
        m.AddImplication(b.scheduled, a.scheduled)
        both = [a.scheduled, b.scheduled]
        m.Add(b.start_day >= a.end_day + dep.min_lag_days).OnlyEnforceIf(both)
        if dep.max_lag_days is not None:
            m.Add(b.start_day <= a.end_day + dep.max_lag_days).OnlyEnforceIf(both)


# 作業者×稼働日ごとの1日作業台数上限制約を追加する（先頭工程のみカウント、部品分譲除外）。
def _add_daily_capacity(ctx: _DayBuildContext) -> None:
    m, p = ctx.model, ctx.problem
    # (worker_id, day_idx) ごとにロック済み台数と非ロック変数項を集計する。
    locked_qty: dict[tuple[int, int], int] = defaultdict(int)
    free_terms: dict[tuple[int, int], list[tuple[Any, int]]] = defaultdict(list)

    for tv in ctx.task_vars.values():
        task = tv.task
        if not task.counts_for_daily_cap:
            continue
        order = p.orders.get(task.order_id)
        if order is None or order.quantity_scaled <= 0:
            continue
        qty = order.quantity_scaled
        if task.lock is not None:
            lk = task.lock
            for d in range(lk.start_day, lk.end_day + 1):
                if 0 <= d < p.num_days:
                    locked_qty[(lk.worker_id, d)] += qty
            continue
        for (wid, start_d), x in tv.slot_vars.items():
            for d in range(start_d, start_d + task.duration_days):
                if 0 <= d < p.num_days:
                    free_terms[(wid, d)].append((x, qty))

    for (wid, d), terms in free_terms.items():
        worker = p.workers.get(wid)
        if worker is None or worker.max_daily_qty is None:
            continue
        # ロック済みタスクだけで既に上限を超えている日は、追加の非ロック割付のみを禁止する。
        remaining = max(0, worker.max_daily_qty - locked_qty.get((wid, d), 0))
        m.Add(sum(qty * x for x, qty in terms) <= remaining)


# リソース×稼働日ごとの1日稼働上限数量（DailyCapacityQuantity）と同時作業数（Capacity）制約を追加する。
def _add_resource_daily_capacity(ctx: _DayBuildContext) -> None:
    m, p = ctx.model, ctx.problem
    locked_qty: dict[tuple[int, int], int] = defaultdict(int)
    locked_cnt: dict[tuple[int, int], int] = defaultdict(int)
    free_qty_terms: dict[tuple[int, int], list[tuple[Any, int]]] = defaultdict(list)
    free_cnt_terms: dict[tuple[int, int], list[Any]] = defaultdict(list)

    for tv in ctx.task_vars.values():
        task = tv.task
        order = p.orders.get(task.order_id)
        qty = order.quantity_scaled if order is not None and order.quantity_scaled > 0 else 0

        if task.lock is not None:
            lk = task.lock
            if lk.resource_id is None:
                continue
            for d in range(lk.start_day, lk.end_day + 1):
                if 0 <= d < p.num_days:
                    locked_cnt[(lk.resource_id, d)] += 1
                    if qty > 0:
                        locked_qty[(lk.resource_id, d)] += qty
            continue

        if not tv.resource_vars:
            continue
        # 上限（台数または件数）が設定されている候補リソースだけ占有変数を作成する。
        bounded_rids = [
            rid for rid in tv.resource_vars
            if rid in p.resources and (
                p.resources[rid].daily_capacity_qty is not None or p.resources[rid].capacity is not None
            )
        ]
        if not bounded_rids:
            continue

        # タスクが各稼働日 d に占有しているかを1つのブール変数へまとめる。
        day_slots: dict[int, list[Any]] = defaultdict(list)
        for (_wid, start_d), x in tv.slot_vars.items():
            for d in range(start_d, start_d + task.duration_days):
                if 0 <= d < p.num_days:
                    day_slots[d].append(x)

        for d, xs in day_slots.items():
            day_act = m.NewBoolVar(f"dda_{task.id}_{d}")
            m.Add(day_act == sum(xs))
            for rid in bounded_rids:
                rv = tv.resource_vars[rid]
                # リソース選択（rv）と稼働日占有（day_act）の論理積を線形制約で表現する。
                used = m.NewBoolVar(f"dru_{task.id}_{rid}_{d}")
                m.Add(used <= rv)
                m.Add(used <= day_act)
                m.Add(used >= rv + day_act - 1)
                res = p.resources[rid]
                if res.daily_capacity_qty is not None and qty > 0:
                    free_qty_terms[(rid, d)].append((used, qty))
                if res.capacity is not None:
                    free_cnt_terms[(rid, d)].append(used)

    # 1日の稼働上限数量制約（リソースを使用する各工程のオーダー数量を合計）。
    for (rid, d), terms in free_qty_terms.items():
        res = p.resources.get(rid)
        if res is None or res.daily_capacity_qty is None:
            continue
        remaining = max(0, res.daily_capacity_qty - locked_qty.get((rid, d), 0))
        m.Add(sum(qty * u for u, qty in terms) <= remaining)

    # 1日の同時作業数制約（リソースを使用する同日タスク件数を合計）。
    for (rid, d), terms in free_cnt_terms.items():
        res = p.resources.get(rid)
        if res is None or res.capacity is None:
            continue
        remaining = max(0, res.capacity - locked_cnt.get((rid, d), 0))
        m.Add(sum(terms) <= remaining)


# 未割付・出荷日超過・標準日からのずれ（前倒し優先）・安定性の目的関数を組み立てる。
def _add_objective(ctx: _DayBuildContext) -> None:
    m, p = ctx.model, ctx.problem
    num_days = max(1, p.num_days)
    max_bound = max(
        num_days + 10,
        max((t.lock.end_day for t in p.tasks.values() if t.lock is not None), default=0) + 10,
    )

    # 既存の分単位計算設定の重みが入っていても、日次モードの優先順位を崩さないよう重みを設定する。
    unsched_w = max(DAY_DEFAULT_WEIGHTS["unscheduled"], ctx.weight("unscheduled"))
    late_w = max(DAY_DEFAULT_WEIGHTS["lateness"], ctx.weight("lateness"))
    late_shift_w = ctx.weight("late_shift")
    early_shift_w = ctx.weight("early_shift")
    mk_w = ctx.weight("makespan")
    stab_w = ctx.weight("stability")

    by_order: dict[int, list[_DayTaskVars]] = defaultdict(list)
    for tv in ctx.task_vars.values():
        by_order[tv.task.order_id].append(tv)
        ctx.add_penalty(1 - tv.scheduled, unsched_w)

    # オーダー単位の出荷日超過（最終工程終了日 > 出荷日 − 1稼働日）
    for order_id, tvs in by_order.items():
        order = p.orders.get(order_id)
        if order is None or order.shipping_day_idx is None:
            continue
        # 出荷日の1稼働日前までを許容上限（遅れ0）とする。
        target_finish = order.shipping_day_idx - 1
        min_end = min([0, target_finish] + [tv.task.lock.end_day for tv in tvs if tv.task.lock is not None])
        order_end = m.NewIntVar(min_end, max_bound, f"doend_{order_id}")
        for tv in tvs:
            m.Add(order_end >= tv.end_day).OnlyEnforceIf(tv.scheduled)
            m.Add(order_end >= num_days).OnlyEnforceIf(tv.scheduled.Not())
        late_days = m.NewIntVar(0, max_bound + abs(target_finish) + 10, f"dlate_{order_id}")
        m.Add(late_days >= order_end - target_finish)
        ctx.add_penalty(late_days, late_w * priority_factor(order.priority) // 10)

    # タスク単位の標準作業日からのずれ（後ろ倒し > 前倒し とし、前倒し分散を優先する）
    for tv in ctx.task_vars.values():
        task = tv.task
        if task.lock is not None:
            continue
        if task.deadline_day_idx is not None:
            t_late = m.NewIntVar(0, max_bound + abs(task.deadline_day_idx) + 10, f"dtlate_{task.id}")
            m.Add(t_late >= tv.end_day - task.deadline_day_idx).OnlyEnforceIf(tv.scheduled)
            ctx.add_penalty(t_late, late_w)

        if task.standard_day_idx is not None:
            # 標準日が計画開始日より前の場合は計画初日（0）を目標日として扱う。
            std = max(0, task.standard_day_idx)
            max_span = max_bound + abs(std) + 10
            early = m.NewIntVar(0, max_span, f"dearly_{task.id}")
            late_s = m.NewIntVar(0, max_span, f"dlshift_{task.id}")
            m.Add(early >= std - tv.start_day).OnlyEnforceIf(tv.scheduled)
            m.Add(late_s >= tv.start_day - std).OnlyEnforceIf(tv.scheduled)
            ctx.add_penalty(early, early_shift_w)
            ctx.add_penalty(late_s, late_shift_w)
        elif mk_w:
            # 標準前倒し日が未設定のタスクは、不要に後ろへ寄らないよう開始日に微小ペナルティを付ける。
            ctx.add_penalty(tv.start_day, mk_w)

        # REPAIRスコープ時は前回計画からの作業日・作業者変更を抑える。
        if stab_w and task.hint is not None:
            dev = m.NewIntVar(0, max_bound + num_days, f"ddev_{task.id}")
            m.Add(dev >= tv.start_day - task.hint.start_day).OnlyEnforceIf(tv.scheduled)
            m.Add(dev >= task.hint.start_day - tv.start_day).OnlyEnforceIf(tv.scheduled)
            ctx.add_penalty(dev, stab_w * 10)
            w_var = tv.worker_vars.get(task.hint.worker_id)
            if w_var is not None:
                ctx.add_penalty(1 - w_var, stab_w * 30)
            if task.hint.resource_id is not None:
                r_var = tv.resource_vars.get(task.hint.resource_id)
                if r_var is not None:
                    ctx.add_penalty(1 - r_var, stab_w * 20)

    if ctx.objective:
        m.Minimize(sum(coef * expr for expr, coef in ctx.objective))


# DayProblem から日次バケット用の CP-SAT モデルを構築する。
def build_day_model(problem: DayProblem) -> _DayBuildContext:
    ctx = _DayBuildContext(problem=problem, model=cp_model.CpModel())
    _add_tasks(ctx)
    _add_same_worker_constraints(ctx)
    _add_dependencies(ctx)
    _add_daily_capacity(ctx)
    _add_resource_daily_capacity(ctx)
    _add_objective(ctx)
    return ctx


# 日次バケット問題を CP-SAT で解き、作業者と稼働日インデックスの割付結果を返す。
def solve_day_problem(
    problem: DayProblem,
    workers: int = 8,
    on_progress: Callable[[dict], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> SolveResult:
    if problem.num_days == 0:
        locked_out = [
            SAssignment(
                task_id=t.id,
                resource_id=t.lock.resource_id,
                start=t.lock.start_day,
                end=t.lock.end_day,
                setup=0,
                locked=True,
                worker_id=t.lock.worker_id,
            )
            for t in problem.tasks.values()
            if t.lock is not None
        ]
        return SolveResult("OPTIMAL", 0.0, 0.0, 0.0, locked_out, ["計画期間内に稼働日がありません"])

    ctx = build_day_model(problem)
    solver = cp_model.CpSolver()
    solver.parameters.num_workers = workers
    if should_stop and should_stop():
        return SolveResult("UNKNOWN", None, None, 0.0, [], ctx.notes)

    finished = Event()
    watcher = (
        Thread(target=watch_cancellation, args=(solver.StopSearch, finished, should_stop), daemon=True)
        if should_stop
        else None
    )
    if watcher:
        watcher.start()
    try:
        status = solver.Solve(ctx.model, _Progress(on_progress))
    finally:
        finished.set()
        if watcher:
            watcher.join()

    name = solver.StatusName(status)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return SolveResult(name, None, None, solver.WallTime(), [], ctx.notes)

    out: list[SAssignment] = []
    for tv in ctx.task_vars.values():
        if not solver.BooleanValue(tv.scheduled):
            continue
        chosen_worker = next(wid for wid, wv in tv.worker_vars.items() if solver.BooleanValue(wv))
        chosen_resource = next((rid for rid, rv in tv.resource_vars.items() if solver.BooleanValue(rv)), None)
        out.append(SAssignment(
            task_id=tv.task.id,
            resource_id=chosen_resource,
            start=solver.Value(tv.start_day),
            end=solver.Value(tv.end_day),
            setup=0,
            locked=tv.task.lock is not None,
            worker_id=chosen_worker,
        ))
    return SolveResult(name, solver.ObjectiveValue(), solver.BestObjectiveBound(), solver.WallTime(), out, ctx.notes)

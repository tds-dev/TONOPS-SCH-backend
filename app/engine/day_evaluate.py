"""日次バケット方式のスケジュール検証と KPI 算出（純粋Python）。

自動計算後の結果評価と、手動編集時の保存前検証で共通使用する。
"""
from collections import defaultdict

from app.core.timeutil import weekday_number
from app.engine.day_problem import DayProblem, fmt_qty
from app.engine.result import SAssignment, Violation
from app.engine.weekdays import DAY_NAMES


# 日次割付と計算条件を照合し、必須違反（HARD）と納期遅れ（SOFT）を返す。
def check_day_schedule(problem: DayProblem, assignments: list[SAssignment]) -> list[Violation]:
    out: list[Violation] = []
    by_task = {a.task_id: a for a in assignments}
    tasks = problem.tasks

    # 未割付タスク
    for task in tasks.values():
        if task.id not in by_task:
            out.append(Violation(
                "HARD", "UNSCHEDULED", f"{task.name}（タスク {task.id}）が未割付です", task_id=task.id
            ))

    # タスク単体の基本条件（作業者・スキル・稼働日・着手可能日・曜日制限）
    for a in assignments:
        task = tasks.get(a.task_id)
        if task is None or a.locked:
            continue
        if a.worker_id is None:
            out.append(Violation("HARD", "NO_WORKER", f"{task.name} に作業者が割り当てられていません", task_id=task.id))
            continue
        worker = problem.workers.get(a.worker_id)
        wname = worker.name if worker else f"作業者 {a.worker_id}"

        if a.worker_id not in task.eligible_worker_ids:
            out.append(Violation(
                "HARD", "NOT_ELIGIBLE", f"{task.name} は {wname} が担当できない工程です", task_id=task.id
            ))
        # 工程にリソース候補が登録されている場合は必須割付・候補内であることを確認する。
        if task.requires_resource:
            if a.resource_id is None:
                out.append(Violation(
                    "HARD", "NO_RESOURCE", f"{task.name} にリソースが割り当てられていません", task_id=task.id
                ))
            elif a.resource_id not in task.eligible_resource_ids:
                res = problem.resources.get(a.resource_id)
                rname = res.name if res else f"リソース {a.resource_id}"
                out.append(Violation(
                    "HARD", "NOT_ELIGIBLE_RESOURCE", f"{task.name} は {rname} で実行できません", task_id=task.id
                ))
        elif a.resource_id is not None:
            res = problem.resources.get(a.resource_id)
            rname = res.name if res else f"リソース {a.resource_id}"
            out.append(Violation(
                "HARD", "NOT_ELIGIBLE_RESOURCE",
                f"{task.name} はリソース指定対象外の工程です（{rname}）", task_id=task.id,
            ))
        if a.start < task.release_day_idx:
            out.append(Violation(
                "HARD", "BEFORE_RELEASE",
                f"{task.name} が着手可能日 {problem.fmt_day(task.release_day_idx)} より前に配置されています",
                task_id=task.id,
            ))

        # 占有する全稼働日が計画期間内かつ作業者の出勤可能日であることを確認する。
        out_of_range = a.start < 0 or a.end >= problem.num_days
        if out_of_range:
            out.append(Violation(
                "HARD", "OUTSIDE_CALENDAR",
                f"{task.name} が計画期間の稼働日外です（{problem.fmt_day(a.start)}）",
                task_id=task.id,
            ))
        else:
            if worker is not None:
                absent_days = [d for d in range(a.start, a.end + 1) if d not in worker.available_days]
                if absent_days:
                    out.append(Violation(
                        "HARD", "OUTSIDE_CALENDAR",
                        f"{task.name} の配置日（{problem.fmt_day(absent_days[0])}）は {wname} の不在日・非稼働日です",
                        task_id=task.id,
                    ))
            if task.allowed_weekdays is not None:
                allowed_set = set(task.allowed_weekdays)
                bad_days = [
                    d for d in range(a.start, a.end + 1)
                    if weekday_number(problem.working_days[d]) not in allowed_set
                ]
                if bad_days:
                    allowed_label = "".join(DAY_NAMES[day] for day in sorted(allowed_set))
                    out.append(Violation(
                        "HARD", "WEEKDAY",
                        f"工程の曜日制限: {task.name} は {allowed_label} のみ実行可能です（{problem.fmt_day(bad_days[0])}）",
                        task_id=task.id,
                    ))
            # 工程終了直後の連休日数（拠点休日＋担当作業者の休み）が上限を超える配置を違反として検出する。
            if task.max_holidays_after is not None:
                holidays = problem.worker_holidays_after(a.worker_id, a.end)
                if holidays is not None and holidays > task.max_holidays_after:
                    out.append(Violation(
                        "HARD", "MAX_HOLIDAYS_AFTER",
                        f"連休前制限: {task.name} は終了後の連休が{task.max_holidays_after}日以内の日のみ配置可能です"
                        f"（{problem.fmt_day(a.end)}の直後は{wname}の休みが{holidays}日間）",
                        task_id=task.id,
                    ))

    # 同一オーダー×同一工程区分の同一作業者チェック
    group_workers: dict[tuple[int, int], list[tuple[int, int]]] = defaultdict(list)
    for a in assignments:
        task = tasks.get(a.task_id)
        if task is None or task.process_group_id is None or a.worker_id is None:
            continue
        group_workers[(task.order_id, task.process_group_id)].append((task.id, a.worker_id))
    for (order_id, _pg_id), entries in group_workers.items():
        distinct = {wid for _, wid in entries}
        if len(distinct) > 1:
            order = problem.orders.get(order_id)
            label = order.no if order else f"オーダー {order_id}"
            names = "・".join(
                problem.workers[wid].name if wid in problem.workers else str(wid)
                for wid in sorted(distinct)
            )
            # 2番目以降のタスクに紐付けて課題一覧から修正箇所を分かりやすくする。
            for tid, _ in entries[1:]:
                out.append(Violation(
                    "HARD", "SAME_WORKER_GROUP",
                    f"{label} の同一工程区分に複数作業者（{names}）が割り当てられています",
                    task_id=tid,
                ))

    # 工程間の順序・稼働日間隔チェック（MinLagDays / MaxLagDays）
    for dep in problem.dependencies:
        p_asgn = by_task.get(dep.pred)
        s_asgn = by_task.get(dep.succ)
        if p_asgn is None or s_asgn is None:
            continue
        gap = s_asgn.start - p_asgn.end
        if gap < dep.min_lag_days:
            out.append(Violation(
                "HARD", "DEPENDENCY",
                f"{tasks[dep.succ].name} は {tasks[dep.pred].name} の後 {dep.min_lag_days}稼働日以上空ける必要があります",
                task_id=dep.succ,
            ))
        if dep.max_lag_days is not None and gap > dep.max_lag_days:
            out.append(Violation(
                "HARD", "MAX_LAG",
                f"{tasks[dep.succ].name} は {tasks[dep.pred].name} の後 {dep.max_lag_days}稼働日以内に開始する必要があります",
                task_id=dep.succ,
            ))

    # 作業者×稼働日ごとの1日作業台数上限チェック（先頭工程のみ・部品分譲除外）
    daily_load: dict[tuple[int, int], int] = defaultdict(int)
    daily_tasks: dict[tuple[int, int], list[int]] = defaultdict(list)
    for a in assignments:
        task = tasks.get(a.task_id)
        if task is None or a.worker_id is None or not task.counts_for_daily_cap:
            continue
        order = problem.orders.get(task.order_id)
        if order is None or order.quantity_scaled <= 0:
            continue
        for d in range(a.start, a.end + 1):
            if 0 <= d < problem.num_days:
                daily_load[(a.worker_id, d)] += order.quantity_scaled
                daily_tasks[(a.worker_id, d)].append(task.id)

    for (wid, d), total_qty in sorted(daily_load.items()):
        worker = problem.workers.get(wid)
        if worker is None or worker.max_daily_qty is None:
            continue
        if total_qty > worker.max_daily_qty:
            out.append(Violation(
                "HARD", "DAILY_CAPACITY_EXCEEDED",
                f"{worker.name} の {problem.fmt_day(d)} 作業台数が上限を超過しています"
                f"（{fmt_qty(total_qty)}台 / 上限 {fmt_qty(worker.max_daily_qty)}台）",
                task_id=daily_tasks[(wid, d)][-1],
            ))

    # リソース×稼働日ごとの1日稼働上限数量・同時作業数チェック（リソースを使用する各工程でカウント）
    res_daily_qty: dict[tuple[int, int], int] = defaultdict(int)
    res_daily_cnt: dict[tuple[int, int], int] = defaultdict(int)
    res_daily_tasks: dict[tuple[int, int], list[int]] = defaultdict(list)
    for a in assignments:
        if a.resource_id is None:
            continue
        task = tasks.get(a.task_id)
        if task is None:
            continue
        order = problem.orders.get(task.order_id)
        qty = order.quantity_scaled if order is not None and order.quantity_scaled > 0 else 0
        for d in range(a.start, a.end + 1):
            if 0 <= d < problem.num_days:
                res_daily_cnt[(a.resource_id, d)] += 1
                if qty > 0:
                    res_daily_qty[(a.resource_id, d)] += qty
                res_daily_tasks[(a.resource_id, d)].append(task.id)

    for (rid, d), total_cnt in sorted(res_daily_cnt.items()):
        res = problem.resources.get(rid)
        if res is None:
            continue
        total_qty = res_daily_qty.get((rid, d), 0)
        if res.daily_capacity_qty is not None and total_qty > res.daily_capacity_qty:
            out.append(Violation(
                "HARD", "RESOURCE_DAILY_QTY_EXCEEDED",
                f"{res.name} の {problem.fmt_day(d)} 稼働数量が上限を超過しています"
                f"（{fmt_qty(total_qty)} / 上限 {fmt_qty(res.daily_capacity_qty)}）",
                task_id=res_daily_tasks[(rid, d)][-1],
            ))
        if res.capacity is not None and total_cnt > res.capacity:
            out.append(Violation(
                "HARD", "RESOURCE_CAPACITY_EXCEEDED",
                f"{res.name} の {problem.fmt_day(d)} 同時作業数が上限を超過しています"
                f"（{total_cnt}件 / 上限 {res.capacity}件）",
                task_id=res_daily_tasks[(rid, d)][-1],
            ))

    # オーダー単位の出荷日超過（SOFT：最終工程終了日 > 出荷日 − 1稼働日）
    order_finish: dict[int, int] = {}
    for a in assignments:
        task = tasks.get(a.task_id)
        if task is not None:
            order_finish[task.order_id] = max(order_finish.get(task.order_id, a.end), a.end)
    for order_id, end_day in order_finish.items():
        order = problem.orders.get(order_id)
        if order is None or order.shipping_day_idx is None:
            continue
        limit_day = order.shipping_day_idx - 1
        if end_day > limit_day:
            late_days = end_day - limit_day
            ship_str = order.shipping_date.strftime("%m/%d") if order.shipping_date else problem.fmt_day(order.shipping_day_idx)
            out.append(Violation(
                "SOFT", "LATE_ORDER",
                f"{order.no} が完了期限を{late_days}稼働日超過（出荷日 {ship_str}）",
                penalty=float(late_days),
            ))

    # タスク単位の完了期限超過（SOFT）
    for task in tasks.values():
        a = by_task.get(task.id)
        if a is not None and task.deadline_day_idx is not None and a.end > task.deadline_day_idx:
            late_days = a.end - task.deadline_day_idx
            out.append(Violation(
                "SOFT", "LATE_TASK",
                f"{task.name} が期限を{late_days}稼働日超過",
                task_id=task.id,
                penalty=float(late_days),
            ))

    return out


# 日次バケット方式の主要KPI（割付件数・納期遅れ・遅れ日数・標準日ずれ・平均負荷率）を集計する。
def compute_day_kpis(problem: DayProblem, assignments: list[SAssignment]) -> dict[str, float]:
    by_task = {a.task_id: a for a in assignments}

    # オーダー別の最終完了稼働日と出荷日超過日数
    order_finish: dict[int, int] = {}
    for a in assignments:
        task = problem.tasks.get(a.task_id)
        if task is not None:
            order_finish[task.order_id] = max(order_finish.get(task.order_id, a.end), a.end)
    lateness_days: list[int] = []
    for order_id, end_day in order_finish.items():
        order = problem.orders.get(order_id)
        if order is not None and order.shipping_day_idx is not None:
            lateness_days.append(max(0, end_day - (order.shipping_day_idx - 1)))

    # 標準作業日からのずれ稼働日数の合計
    shift_days = 0
    for a in assignments:
        task = problem.tasks.get(a.task_id)
        if task is not None and task.standard_day_idx is not None:
            shift_days += abs(a.start - max(0, task.standard_day_idx))

    # 1日台数上限が設定されている作業者の、出勤日総能力に対する平均台数負荷率（%）
    total_cap = sum(
        w.max_daily_qty * len(w.available_days)
        for w in problem.workers.values()
        if w.max_daily_qty is not None and w.available_days
    )
    used_cap = 0
    for a in assignments:
        task = problem.tasks.get(a.task_id)
        if task is None or a.worker_id is None or not task.counts_for_daily_cap:
            continue
        worker = problem.workers.get(a.worker_id)
        order = problem.orders.get(task.order_id)
        if worker is None or worker.max_daily_qty is None or order is None:
            continue
        in_range_days = sum(1 for d in range(a.start, a.end + 1) if 0 <= d < problem.num_days)
        used_cap += order.quantity_scaled * in_range_days

    return {
        "割付済みタスク": float(len(by_task)),
        "未割付タスク": float(sum(1 for tid in problem.tasks if tid not in by_task)),
        "納期遅れ": float(sum(1 for x in lateness_days if x > 0)),
        "遅れ日数の合計": float(sum(lateness_days)),
        "標準日からのずれ日数": float(shift_days),
        "平均負荷率": round(100.0 * used_cap / total_cap, 1) if total_cap else 0.0,
    }

"""スケジュールを Problem と照合して検証し、KPI を算出する（純粋 Python）。

毎回の計算後（KPI と課題一覧）と、フェーズ3 で手動のドラッグ＆ドロップを
保存する前の検証に使う。
"""
from collections import defaultdict
from itertools import pairwise

from app.engine.problem import Problem
from app.engine.result import SAssignment, Violation, fmt, fmt_duration
from app.engine.rules import get_plugin

__all__ = ["SAssignment", "Violation", "check_schedule", "compute_kpis", "job_finishes"]


def _inside(windows: list[tuple[int, int]], s: int, e: int) -> bool:
    return any(ws <= s and e <= we for ws, we in windows)


def check_schedule(problem: Problem, assignments: list[SAssignment]) -> list[Violation]:
    out: list[Violation] = []
    by_task = {a.task_id: a for a in assignments}
    tasks = problem.tasks

    # 未割付のタスク
    for t in tasks.values():
        if t.id not in by_task:
            out.append(Violation("HARD", "UNSCHEDULED", f"{t.name}（タスク {t.id}）が未割付です", task_id=t.id))

    for a in assignments:
        t = tasks.get(a.task_id)
        if t is None:
            continue
        res = problem.resources.get(a.resource_id)
        if a.locked:
            continue  # ロック済みの作業はそのまま受け入れる
        if not any(o.resource_id == a.resource_id for o in t.options):
            out.append(Violation("HARD", "NOT_ELIGIBLE", f"{t.name} は {res.name if res else a.resource_id} で実行できません", task_id=t.id))
        if res and not _inside(res.windows, a.start, a.end):
            out.append(Violation("HARD", "OUTSIDE_CALENDAR", f"{t.name} が {res.name} の稼働時間外です（{fmt(problem, a.start)}）", task_id=t.id))
        if a.start < t.release:
            out.append(Violation("HARD", "BEFORE_RELEASE", f"{t.name} が着手可能日時 {fmt(problem, t.release)} より前に開始しています", task_id=t.id))

    # 単一能力リソースの重なり（段取り時間も占有として扱う）
    per_res: dict[int, list[SAssignment]] = defaultdict(list)
    for a in assignments:
        per_res[a.resource_id].append(a)
    for rid, items in per_res.items():
        res = problem.resources.get(rid)
        if res is None or res.capacity != 1:
            continue
        items.sort(key=lambda x: x.start)
        for prev, cur in pairwise(items):
            if cur.start - cur.setup < prev.end:
                out.append(Violation("HARD", "OVERLAP", f"{res.name} で {fmt(problem, cur.start)} に作業が重なっています", task_id=cur.task_id))
        # 連続するタスク間の段取り替えチェック
        for co in problem.changeovers:
            if rid not in co.resource_ids:
                continue
            for prev, cur in pairwise(items):
                pv = tasks[prev.task_id].attrs.get(co.attribute) if prev.task_id in tasks else None
                cv = tasks[cur.task_id].attrs.get(co.attribute) if cur.task_id in tasks else None
                if pv is None or cv is None:
                    continue
                need, forbidden = co.lookup(pv, cv)
                if forbidden:
                    out.append(Violation("HARD", "FORBIDDEN_SEQUENCE", f"{res.name}: {co.attribute} {pv}→{cv} の順序は禁止されています", task_id=cur.task_id))
                elif cur.start - prev.end < need:
                    out.append(Violation("HARD", "SETUP_TOO_SHORT", f"{res.name}: {pv}→{cv} の段取りに {need}分必要です", task_id=cur.task_id))

    # 依存関係
    for d in problem.dependencies:
        p, s = by_task.get(d.pred), by_task.get(d.succ)
        if p is None or s is None:
            continue
        ref = {"FS": (p.end, s.start), "SS": (p.start, s.start), "FF": (p.end, s.end), "SF": (p.start, s.end)}[d.type]
        gap = ref[1] - ref[0]
        if gap < d.lag:
            out.append(Violation("HARD", "DEPENDENCY", f"{tasks[d.succ].name} は {tasks[d.pred].name} の後 {d.lag}分以上空ける必要があります", task_id=d.succ))
        if d.max_lag is not None and gap > d.max_lag:
            out.append(Violation("HARD", "MAX_LAG", f"{tasks[d.succ].name} は {tasks[d.pred].name} の後 {d.max_lag}分以内に開始する必要があります", task_id=d.succ))

    # ルールプラグイン
    for rule in problem.rules:
        plugin = get_plugin(rule.type_key)
        if plugin is not None:
            out.extend(plugin.check(problem, rule, assignments))

    # ジョブ・タスクの納期遅れ（推奨扱い: 許容するがコストになる）
    for job_id, end, due in job_finishes(problem, by_task):
        if due is not None and end > due:
            job = problem.jobs[job_id]
            out.append(Violation("SOFT", "LATE_JOB", f"{job.no} が{fmt_duration(end - due)}遅れ（納期 {fmt(problem, due)}）", penalty=end - due))
    for t in tasks.values():
        a = by_task.get(t.id)
        if a and t.deadline is not None and a.end > t.deadline:
            out.append(Violation("SOFT", "LATE_TASK", f"{t.name} が期限を{fmt_duration(a.end - t.deadline)}超過", task_id=t.id, penalty=a.end - t.deadline))
    return out


def job_finishes(problem: Problem, by_task: dict[int, SAssignment]) -> list[tuple[int, int, int | None]]:
    """(job_id, 完了分, 納期分) を、割付済みタスクが 1 件以上あるジョブについて返す。"""
    finish: dict[int, int] = {}
    for a in by_task.values():
        t = problem.tasks.get(a.task_id)
        if t:
            finish[t.job_id] = max(finish.get(t.job_id, a.end), a.end)
    return [(j, f, problem.jobs[j].due if j in problem.jobs else None) for j, f in finish.items()]


def compute_kpis(problem: Problem, assignments: list[SAssignment]) -> dict[str, float]:
    by_task = {a.task_id: a for a in assignments}
    finishes = job_finishes(problem, by_task)
    lateness = [max(0, f - d) for _, f, d in finishes if d is not None]
    working = sum(we - ws for r in problem.resources.values() for ws, we in r.windows)
    busy = sum(a.end - a.start for a in assignments)
    return {
        "scheduled_tasks": float(len(by_task)),
        "unscheduled_tasks": float(sum(1 for t in problem.tasks if t not in by_task)),
        "late_jobs": float(sum(1 for x in lateness if x > 0)),
        "total_lateness_min": float(sum(lateness)),
        "makespan_min": float(max((a.end for a in assignments), default=0)),
        "setup_min": float(sum(a.setup for a in assignments)),
        "utilisation_pct": round(100.0 * busy / working, 1) if working else 0.0,
    }

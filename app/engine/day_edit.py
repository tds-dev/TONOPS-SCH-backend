"""日次バケット方式の手動編集（純粋関数、DB・OR-Tools非依存）。

作業日・作業者の変更、配置、解除、ロックを割付リストへ適用し、
変更前後で新たに発生した違反だけを返す。
"""
from collections import Counter
from dataclasses import dataclass, replace

from app.engine.day_evaluate import check_day_schedule
from app.engine.day_problem import DayProblem
from app.engine.result import SAssignment, Violation


@dataclass
class DayChange:
    """日単位計画の1件の手動編集内容。"""

    task_id: int
    worker_id: int | None = None  # None = 変更しない
    resource_id: int | None = None  # None = 変更しない（未割付配置時はリソース必須工程のみ指定）
    start_day: int | None = None  # 稼働日インデックス。None = 変更しない
    end_day: int | None = None  # 稼働日インデックス（閉区間）。None = 所要稼働日数を維持
    lock: bool | None = None
    remove: bool = False


# 日単位割付の変更を適用した新しい割付リストを返す。
def apply_day_changes(
    problem: DayProblem,
    assignments: list[SAssignment],
    changes: list[DayChange],
    lock_moved: bool = True,
) -> tuple[list[SAssignment], set[int], list[str]]:
    by_task = {a.task_id: replace(a) for a in assignments}
    changed: set[int] = set()
    errors: list[str] = []

    for c in changes:
        task = problem.tasks.get(c.task_id)
        name = task.name if task else f"タスク {c.task_id}"
        cur = by_task.get(c.task_id)

        if c.remove:
            if cur is None:
                errors.append(f"{name} は割付されていません")
                continue
            if cur.locked and c.lock is not False:
                errors.append(f"{name} はロックされています。先にロックを解除してください")
                continue
            changed.add(c.task_id)
            del by_task[c.task_id]
            continue

        moving = (
            c.worker_id is not None
            or c.resource_id is not None
            or c.start_day is not None
            or c.end_day is not None
        )
        if cur is None:
            if task is None:
                errors.append(f"{name} はこの計画の対象外です")
                continue
            if c.worker_id is None or c.start_day is None:
                errors.append(f"{name} を配置するには作業者と作業日が必要です")
                continue
            if c.worker_id not in problem.workers:
                errors.append(f"{name} に指定された作業者が存在しません")
                continue
            if task.requires_resource and c.resource_id is None:
                errors.append(f"{name} を配置するにはリソースの指定が必要です")
                continue
            if c.resource_id is not None and c.resource_id not in problem.resources:
                errors.append(f"{name} に指定されたリソースが存在しません")
                continue
            rid = c.resource_id if task.requires_resource else None
            end_day = c.end_day if c.end_day is not None else c.start_day + task.duration_days - 1
            new = SAssignment(
                task_id=c.task_id,
                resource_id=rid,
                start=c.start_day,
                end=end_day,
                setup=0,
                locked=lock_moved,
                worker_id=c.worker_id,
            )
        else:
            if cur.locked and moving and c.lock is not False:
                errors.append(f"{name} はロックされています。先にロックを解除してください")
                continue
            wid = c.worker_id if c.worker_id is not None else cur.worker_id
            if wid is not None and wid not in problem.workers:
                errors.append(f"{name} に指定された作業者が存在しません")
                continue
            rid = c.resource_id if c.resource_id is not None else cur.resource_id
            if rid is not None and rid not in problem.resources:
                errors.append(f"{name} に指定されたリソースが存在しません")
                continue
            start_day = c.start_day if c.start_day is not None else cur.start
            if c.end_day is not None:
                end_day = c.end_day
            else:
                span = (task.duration_days - 1) if task is not None else (cur.end - cur.start)
                end_day = start_day + span
            new = replace(cur, resource_id=rid, worker_id=wid, start=start_day, end=end_day, setup=0)
            if moving:
                new.locked = lock_moved or cur.locked

        if new.end < new.start:
            errors.append(f"{name} の終了日は開始日以降にしてください")
            continue
        if c.lock is not None:
            new.locked = c.lock
        changed.add(c.task_id)
        by_task[c.task_id] = new

    return list(by_task.values()), changed, errors


def _key(v: Violation) -> tuple:
    # 日上限超過は作業者・リソース・日付ごとにメッセージ単位で区別し、悪化・新規超過を確実に検出する。
    if v.code in {"DAILY_CAPACITY_EXCEEDED", "RESOURCE_DAILY_QTY_EXCEEDED", "RESOURCE_CAPACITY_EXCEEDED"} or v.task_id is None:
        return (v.severity, v.code, v.task_id, v.message)
    return (v.severity, v.code, v.task_id, "")


# 変更前後を比較し、新たに発生した違反だけを返す。
def new_day_violations(
    problem: DayProblem, before: list[SAssignment], after: list[SAssignment]
) -> list[Violation]:
    def checked(records: list[SAssignment]) -> list[Violation]:
        return check_day_schedule(problem, [replace(a, locked=False) for a in records])

    old = Counter(_key(v) for v in checked(before))
    out: list[Violation] = []
    for v in checked(after):
        k = _key(v)
        if old[k] > 0:
            old[k] -= 1
        else:
            out.append(v)
    return out

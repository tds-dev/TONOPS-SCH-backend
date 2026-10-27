"""計画ボードでの手動編集（純粋関数、DB・OR-Tools 非依存）。

    apply_changes()     変更（移動・リサイズ・配置・削除・ロック）を割付リストに適用
    recompute_setups()  変更したリソースの段取り時間を段取り替えマトリクスから再計算
    new_violations()    変更前後の違反を比較し、新たに発生したものだけを返す

ロック済みの割付は、ソルバーでは「そのまま受け入れる」扱いだが、手動編集の
検証ではすべての割付をチェック対象にする（変更前後の差分を取るので、既存の
違反で操作がブロックされることはない）。
"""
from collections import Counter
from dataclasses import dataclass, replace

from app.engine.evaluate import check_schedule
from app.engine.problem import PChangeover, Problem
from app.engine.result import SAssignment, Violation


@dataclass
class Change:
    task_id: int
    resource_id: int | None = None  # None = 変更しない
    start: int | None = None  # 分。None = 変更しない
    end: int | None = None  # 分。指定時はリサイズ、None なら所要時間を維持
    lock: bool | None = None  # None = 変更しない
    remove: bool = False  # True = 割付を外す（未割付に戻す）


def option_duration(problem: Problem, task_id: int, resource_id: int) -> int | None:
    task = problem.tasks.get(task_id)
    if task is None:
        return None
    return next((o.duration for o in task.options if o.resource_id == resource_id), None)


def _changeover_for(problem: Problem, resource_id: int) -> PChangeover | None:
    return next((c for c in problem.changeovers if resource_id in c.resource_ids), None)


def recompute_setups(problem: Problem, assignments: list[SAssignment], resource_ids: set[int]) -> None:
    """指定リソース上の割付を開始順に並べ、直前タスクとの段取り時間を設定し直す。"""
    for rid in resource_ids:
        items = sorted((a for a in assignments if a.resource_id == rid), key=lambda a: a.start)
        co = _changeover_for(problem, rid)
        prev = None
        for a in items:
            need = 0
            if co is not None and prev is not None:
                pt, ct = problem.tasks.get(prev.task_id), problem.tasks.get(a.task_id)
                pv = pt.attrs.get(co.attribute) if pt else None
                cv = ct.attrs.get(co.attribute) if ct else None
                if pv is not None and cv is not None:
                    need, _ = co.lookup(pv, cv)
            a.setup = need
            prev = a


def apply_changes(
    problem: Problem, assignments: list[SAssignment], changes: list[Change], lock_moved: bool = True
) -> tuple[list[SAssignment], set[int], set[int], list[str]]:
    """変更を適用した新しい割付リストを返す。

    戻り値: (割付リスト, 影響を受けたリソースID, 変更したタスクID, エラーメッセージ)
    エラーがある場合、その変更は適用しない。
    """
    by_task = {a.task_id: replace(a) for a in assignments}
    affected: set[int] = set()
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
            affected.add(cur.resource_id)
            changed.add(c.task_id)
            del by_task[c.task_id]
            continue

        moving = c.resource_id is not None or c.start is not None or c.end is not None
        if cur is None:
            # 未割付タスクをボードに配置
            if task is None:
                errors.append(f"{name} はこの計画の対象外です")
                continue
            if c.resource_id is None or c.start is None:
                errors.append(f"{name} を配置するにはリソースと開始時刻が必要です")
                continue
            dur = option_duration(problem, c.task_id, c.resource_id)
            if dur is None and c.end is None:
                errors.append(f"{name} はこのリソースで実行できません")
                continue
            end = c.end if c.end is not None else c.start + dur
            new = SAssignment(c.task_id, c.resource_id, c.start, end, locked=lock_moved)
        else:
            if cur.locked and moving and c.lock is not False:
                errors.append(f"{name} はロックされています。先にロックを解除してください")
                continue
            rid = c.resource_id if c.resource_id is not None else cur.resource_id
            start = c.start if c.start is not None else cur.start
            if c.end is not None:
                end = c.end
            elif rid != cur.resource_id:
                dur = option_duration(problem, c.task_id, rid)
                end = start + (dur if dur is not None else cur.end - cur.start)
            else:
                end = start + (cur.end - cur.start)
            new = replace(cur, resource_id=rid, start=start, end=end)
            if moving:
                new.locked = lock_moved or cur.locked
            affected.add(cur.resource_id)
        if new.end <= new.start:
            errors.append(f"{name} の終了は開始より後にしてください")
            continue
        if c.lock is not None:
            new.locked = c.lock
        affected.add(new.resource_id)
        changed.add(c.task_id)
        by_task[c.task_id] = new

    result = list(by_task.values())
    recompute_setups(problem, result, affected)
    return result, affected, changed, errors


def _key(v: Violation) -> tuple:
    # タスクに紐づく違反はコード単位で比較（メッセージ内の時刻の変化を無視）。
    # ジョブの納期遅れなどタスクに紐づかないものはメッセージごと比較し、遅れの増加を検出する。
    return (v.severity, v.code, v.task_id, v.rule_id, "" if v.task_id is not None else v.message)


def new_violations(problem: Problem, before: list[SAssignment], after: list[SAssignment]) -> list[Violation]:
    """変更後に新たに発生した違反（変更前にはなかったもの）。"""

    def checked(items: list[SAssignment]) -> list[Violation]:
        return check_schedule(problem, [replace(a, locked=False) for a in items])

    old = Counter(_key(v) for v in checked(before))
    out = []
    for v in checked(after):
        k = _key(v)
        if old[k] > 0:
            old[k] -= 1
        else:
            out.append(v)
    return out

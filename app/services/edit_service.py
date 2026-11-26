"""計画ボードからの手動編集（検証と保存）。

時刻の扱い: ボードは拠点の現地時刻で表示するため、オフセットなしの日時は
拠点の現地時刻とみなす。オフセット付き（"...+09:00" や "...Z"）はそのまま変換する。
"""
from dataclasses import dataclass, field
from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.timeutil import to_jst_naive
from app.engine.day_edit import DayChange, apply_day_changes, new_day_violations
from app.engine.day_evaluate import compute_day_kpis
from app.engine.day_problem import DayProblem
from app.engine.day_snapshot import build_day_problem
from app.engine.edit import Change, apply_changes, new_violations
from app.engine.evaluate import compute_kpis
from app.engine.problem import Problem
from app.engine.result import SAssignment, Violation
from app.engine.snapshot import build_problem
from app.engine.solve import is_day_mode, write_day_evaluation, write_evaluation
from app.models.transactions import Plan, PlanAssignment
from app.services.plan_lifecycle import NON_BLOCKING_HARD


# 割付IDやタスクIDを使って指定する手動編集の要求。
@dataclass
class ChangeRequest:
    assignment_id: int | None = None
    task_id: int | None = None
    resource_id: int | None = None
    # 日単位計画での作業者変更・配置に使う作業者ID。
    worker_id: int | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    is_locked: bool | None = None
    remove: bool = False


# 手動編集の検証で得た割付・違反・評価値。
@dataclass
class EditResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    hard: list[Violation] = field(default_factory=list)
    soft: list[Violation] = field(default_factory=list)
    kpis: dict[str, float] = field(default_factory=dict)
    changed_task_ids: list[int] = field(default_factory=list)


# 手動編集の検証に使う計算条件と現在の割付を読み込む。
def _load(db: Session, plan: Plan) -> tuple[Problem, dict[int, PlanAssignment], list[SAssignment]]:
    problem = build_problem(db, plan)
    rows = {a.TaskID: a for a in db.scalars(select(PlanAssignment).where(PlanAssignment.PlanID == plan.PlanID))}
    current = [
        SAssignment(a.TaskID, a.ResourceID, problem.to_min(a.StartAt), problem.to_min(a.EndAt),
                    int(a.SetupMinutes or 0), bool(a.IsLocked))
        for a in rows.values()
    ]
    return problem, rows, current


# 手動編集の対象タスクIDを解決する。
def _resolve_task_id(by_id: dict[int, PlanAssignment], r: ChangeRequest) -> int:
    if r.assignment_id is not None:
        row = by_id.get(r.assignment_id)
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"割付 {r.assignment_id} はこの計画にありません")
        return row.TaskID
    if r.task_id is not None:
        return r.task_id
    raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "assignmentId または taskId が必要です")


# 画面から受け取った変更要求を、アプリ共通の時刻設定で検証用の形式へ変換する。
def _to_changes(problem: Problem, rows: dict[int, PlanAssignment],
                requests: list[ChangeRequest]) -> list[Change]:
    by_id = {a.AssignmentID: a for a in rows.values()}
    out = []
    for r in requests:
        task_id = _resolve_task_id(by_id, r)
        out.append(Change(
            task_id=task_id,
            resource_id=r.resource_id,
            start=problem.to_min(to_jst_naive(r.start_at)) if r.start_at else None,
            end=problem.to_min(to_jst_naive(r.end_at)) if r.end_at else None,
            lock=r.is_locked,
            remove=r.remove,
        ))
    return out


# 日次モードの手動編集用に、DayProblem と現在の割付一覧を読み込む。
def _load_day(db: Session, plan: Plan) -> tuple[DayProblem, dict[int, PlanAssignment], list[SAssignment]]:
    problem = build_day_problem(db, plan)
    rows = {a.TaskID: a for a in db.scalars(select(PlanAssignment).where(PlanAssignment.PlanID == plan.PlanID))}
    current: list[SAssignment] = []
    for a in rows.values():
        s_day = problem.dt_to_day_idx(a.StartAt)
        e_day = problem.end_dt_to_day_idx(a.EndAt)
        if s_day is None or e_day is None:
            continue
        current.append(SAssignment(
            a.TaskID, a.ResourceID, s_day, e_day, 0, bool(a.IsLocked), worker_id=a.WorkerID
        ))
    return problem, rows, current


# 日次モードの変更要求を稼働日インデックスへ変換し、非稼働日指定はエラーとして返す。
def _to_day_changes(
    problem: DayProblem, rows: dict[int, PlanAssignment], requests: list[ChangeRequest]
) -> tuple[list[DayChange], list[str]]:
    by_id = {a.AssignmentID: a for a in rows.values()}
    out: list[DayChange] = []
    errors: list[str] = []
    for r in requests:
        task_id = _resolve_task_id(by_id, r)
        task = problem.tasks.get(task_id)
        label = task.name if task else f"タスク {task_id}"
        start_day: int | None = None
        end_day: int | None = None
        if r.start_at is not None:
            dt = to_jst_naive(r.start_at)
            start_day = problem.dt_to_day_idx(dt)
            if start_day is None:
                errors.append(f"{label} の開始日（{dt.strftime('%m/%d')}）は非稼働日または計画期間外です")
                continue
        if r.end_at is not None:
            dt = to_jst_naive(r.end_at)
            end_day = problem.end_dt_to_day_idx(dt)
            if end_day is None:
                errors.append(f"{label} の終了日（{dt.strftime('%m/%d')}）は非稼働日または計画期間外です")
                continue
        out.append(DayChange(
            task_id=task_id,
            worker_id=r.worker_id,
            resource_id=r.resource_id,
            start_day=start_day,
            end_day=end_day,
            lock=r.is_locked,
            remove=r.remove,
        ))
    return out, errors


def evaluate_edit(db: Session, plan: Plan, requests: list[ChangeRequest], lock_moved: bool = True):
    if plan.Status != "DRAFT":
        raise HTTPException(status.HTTP_409_CONFLICT, f"下書きの計画のみ編集できます（現在: {plan.Status}）")
    if is_day_mode(db, plan):
        problem, rows, current = _load_day(db, plan)
        changes, conv_errors = _to_day_changes(problem, rows, requests)
        after, changed, apply_errors = apply_day_changes(problem, current, changes, lock_moved=lock_moved)
        errors = conv_errors + apply_errors
        found = new_day_violations(problem, current, after) if not errors else []
        blocking = [v for v in found if v.severity == "HARD" and v.code not in NON_BLOCKING_HARD]
        result = EditResult(
            ok=not errors and not blocking,
            errors=errors,
            hard=blocking,
            soft=[v for v in found if v not in blocking],
            kpis=compute_day_kpis(problem, after),
            changed_task_ids=sorted(changed),
        )
        return result, problem, rows, current, after

    problem, rows, current = _load(db, plan)
    changes = _to_changes(problem, rows, requests)
    after, _, changed, errors = apply_changes(problem, current, changes, lock_moved=lock_moved)
    found = new_violations(problem, current, after) if not errors else []
    # 未割付（タスクを外した結果）は保存を妨げない。承認時と同じ扱い
    blocking = [v for v in found if v.severity == "HARD" and v.code not in NON_BLOCKING_HARD]
    result = EditResult(
        ok=not errors and not blocking,
        errors=errors,
        hard=blocking,
        soft=[v for v in found if v not in blocking],
        kpis=compute_kpis(problem, after),
        changed_task_ids=sorted(changed),
    )
    return result, problem, rows, current, after


def save_edit(db: Session, plan: Plan, requests: list[ChangeRequest], user: str,
              lock_moved: bool = True, force: bool = False) -> EditResult:
    result, problem, rows, current, after = evaluate_edit(db, plan, requests, lock_moved)
    if result.errors:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, {"message": "変更を適用できません", "errors": result.errors})
    if result.hard and not force:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            {"message": "必須制約の違反が発生します。force=true で保存できます",
             "violations": [v.message for v in result.hard]},
        )
    before = {a.task_id: a for a in current}
    new = {a.task_id: a for a in after}
    day_mode = isinstance(problem, DayProblem)
    for task_id, row in rows.items():
        if task_id not in new:
            db.delete(row)  # 割付を外した
            continue
        a, b = new[task_id], before.get(task_id)
        if day_mode:
            moved = b is None or (a.worker_id, a.resource_id, a.start, a.end) != (b.worker_id, b.resource_id, b.start, b.end)
            if moved or b is None or a.locked != b.locked:
                row.ResourceID = a.resource_id
                row.WorkerID = a.worker_id
                row.StartAt = problem.day_to_start_dt(a.start)
                row.EndAt = problem.day_to_end_dt(a.end)
                row.SetupMinutes, row.IsLocked = 0, a.locked
                if moved:
                    row.Source = "MANUAL"
                row.UpdatedBy = user
        else:
            moved = b is None or (a.resource_id, a.start, a.end) != (b.resource_id, b.start, b.end)
            if moved or b is None or a.locked != b.locked or a.setup != b.setup:
                row.ResourceID = a.resource_id
                row.StartAt, row.EndAt = problem.to_dt(a.start), problem.to_dt(a.end)
                row.SetupMinutes, row.IsLocked = a.setup, a.locked
                if moved:
                    row.Source = "MANUAL"
                row.UpdatedBy = user
    for task_id, a in new.items():
        if task_id not in rows:  # 未割付タスクを配置した
            if day_mode:
                db.add(PlanAssignment(
                    PlanID=plan.PlanID, TaskID=task_id, ResourceID=a.resource_id, WorkerID=a.worker_id,
                    StartAt=problem.day_to_start_dt(a.start), EndAt=problem.day_to_end_dt(a.end),
                    SetupMinutes=0, IsLocked=a.locked, Source="MANUAL", CreatedBy=user,
                ))
            else:
                db.add(PlanAssignment(
                    PlanID=plan.PlanID, TaskID=task_id, ResourceID=a.resource_id,
                    StartAt=problem.to_dt(a.start), EndAt=problem.to_dt(a.end), SetupMinutes=a.setup,
                    IsLocked=a.locked, Source="MANUAL", CreatedBy=user,
                ))
    db.flush()
    if day_mode:
        write_day_evaluation(db, plan, problem, after, user)
    else:
        write_evaluation(db, plan, problem, after, user)
    plan.UpdatedBy = user
    db.commit()
    return result

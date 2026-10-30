"""計画ボードからの手動編集（検証と保存）。

時刻の扱い: ボードは拠点の現地時刻で表示するため、オフセットなしの日時は
拠点の現地時刻とみなす。オフセット付き（"...+09:00" や "...Z"）はそのまま変換する。
"""
from dataclasses import dataclass, field
from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.timeutil import to_utc_naive
from app.engine.edit import Change, apply_changes, new_violations
from app.engine.evaluate import compute_kpis
from app.engine.problem import Problem
from app.engine.result import SAssignment, Violation
from app.engine.snapshot import build_problem
from app.engine.solve import write_evaluation
from app.models.masters import Location
from app.models.transactions import Plan, PlanAssignment
from app.services.plan_lifecycle import NON_BLOCKING_HARD


# 割付IDやタスクIDを使って指定する手動編集の要求。
@dataclass
class ChangeRequest:
    assignment_id: int | None = None
    task_id: int | None = None
    resource_id: int | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    is_locked: bool | None = None
    remove: bool = False
    row_ver: int | None = None


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


# 画面から受け取った変更要求を、拠点の時刻設定で検証用の形式へ変換する。
def _to_changes(db: Session, plan: Plan, problem: Problem, rows: dict[int, PlanAssignment],
                requests: list[ChangeRequest]) -> list[Change]:
    tz = db.get(Location, plan.LocationID).TimeZone
    by_id = {a.AssignmentID: a for a in rows.values()}
    out = []
    for r in requests:
        if r.assignment_id is not None:
            row = by_id.get(r.assignment_id)
            if row is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, f"割付 {r.assignment_id} はこの計画にありません")
            if r.row_ver is not None and r.row_ver != row.RowVer:
                raise HTTPException(status.HTTP_409_CONFLICT, "他のユーザーが先に更新しました。再読み込みしてください")
            task_id = row.TaskID
        elif r.task_id is not None:
            task_id = r.task_id
        else:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "assignmentId または taskId が必要です")
        out.append(Change(
            task_id=task_id,
            resource_id=r.resource_id,
            start=problem.to_min(to_utc_naive(r.start_at, tz)) if r.start_at else None,
            end=problem.to_min(to_utc_naive(r.end_at, tz)) if r.end_at else None,
            lock=r.is_locked,
            remove=r.remove,
        ))
    return out


def evaluate_edit(db: Session, plan: Plan, requests: list[ChangeRequest], lock_moved: bool = True):
    if plan.Status != "DRAFT":
        raise HTTPException(status.HTTP_409_CONFLICT, f"下書きの計画のみ編集できます（現在: {plan.Status}）")
    problem, rows, current = _load(db, plan)
    changes = _to_changes(db, plan, problem, rows, requests)
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
    for task_id, row in rows.items():
        if task_id not in new:
            db.delete(row)  # 割付を外した
            continue
        a, b = new[task_id], before[task_id]
        moved = (a.resource_id, a.start, a.end) != (b.resource_id, b.start, b.end)
        if moved or a.locked != b.locked or a.setup != b.setup:
            row.ResourceID = a.resource_id
            row.StartAt, row.EndAt = problem.to_dt(a.start), problem.to_dt(a.end)
            row.SetupMinutes, row.IsLocked = a.setup, a.locked
            if moved:
                row.Source = "MANUAL"
            row.UpdatedBy = user
    for task_id, a in new.items():
        if task_id not in rows:  # 未割付タスクを配置した
            db.add(PlanAssignment(
                PlanID=plan.PlanID, TaskID=task_id, ResourceID=a.resource_id,
                StartAt=problem.to_dt(a.start), EndAt=problem.to_dt(a.end), SetupMinutes=a.setup,
                IsLocked=a.locked, Source="MANUAL", CreatedBy=user,
            ))
    db.flush()
    write_evaluation(db, plan, problem, after, user)
    plan.UpdatedBy = user
    db.commit()
    return result

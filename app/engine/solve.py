"""ソルバー実行を 1 件、最後まで処理する: スナップショット → CP-SAT → 結果の書込み。

計画に書き込む結果:
  T_PlanAssignments  置換（ロック行は IsLocked / Source を保持）
  T_PlanKpis         置換
  T_PlanViolations   置換（納期遅れ、未割付タスク、ルール違反）
"""
import time
import traceback
from collections.abc import Callable

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.timeutil import utcnow
from app.engine.evaluate import check_schedule, compute_kpis
from app.engine.problem import Problem
from app.engine.result import SAssignment
from app.engine.snapshot import build_problem
from app.models.transactions import Plan, PlanAssignment, PlanKpi, PlanViolation, SolverRun

PROGRESS_EVERY_SEC = 1.0
CANCEL_CHECK_EVERY_SEC = 2.0


def write_results(db: Session, plan: Plan, problem: Problem, assignments: list[SAssignment], user: str) -> None:
    def rows_of(plan_id):
        if plan_id is None:
            return {}
        return {a.TaskID: a for a in db.scalars(select(PlanAssignment).where(PlanAssignment.PlanID == plan_id))}

    own, base = rows_of(plan.PlanID), rows_of(plan.BasePlanID)
    db.execute(delete(PlanAssignment).where(PlanAssignment.PlanID == plan.PlanID))
    db.flush()
    for a in assignments:
        prev = own.get(a.task_id) or base.get(a.task_id)
        locked = bool(prev and prev.IsLocked)
        db.add(PlanAssignment(
            PlanID=plan.PlanID, TaskID=a.task_id, ResourceID=a.resource_id,
            StartAt=problem.to_dt(a.start), EndAt=problem.to_dt(a.end), SetupMinutes=a.setup,
            IsLocked=locked, Source=(prev.Source if locked and prev else "SOLVER"), CreatedBy=user,
        ))

    db.execute(delete(PlanKpi).where(PlanKpi.PlanID == plan.PlanID))
    for key, value in compute_kpis(problem, assignments).items():
        db.add(PlanKpi(PlanID=plan.PlanID, KpiKey=key, KpiValue=value))

    db.execute(delete(PlanViolation).where(PlanViolation.PlanID == plan.PlanID))
    for v in check_schedule(problem, assignments):
        db.add(PlanViolation(
            PlanID=plan.PlanID, RuleID=v.rule_id, TaskID=v.task_id, Severity=v.severity,
            Penalty=v.penalty, Message=v.message[:500], CreatedBy=user,
        ))


def _progress_writer(factory: sessionmaker, run_id: int) -> Callable[[dict], None]:
    last = [0.0]

    def write(progress: dict) -> None:
        now = time.monotonic()
        if now - last[0] < PROGRESS_EVERY_SEC:
            return
        last[0] = now
        with factory() as s:
            run = s.get(SolverRun, run_id)
            if run is not None:
                run.ProgressJSON = progress
                s.commit()

    return write


def _cancel_checker(factory: sessionmaker, run_id: int) -> Callable[[], bool]:
    last = [0.0]
    cancelled = [False]

    def check() -> bool:
        now = time.monotonic()
        if not cancelled[0] and now - last[0] >= CANCEL_CHECK_EVERY_SEC:
            last[0] = now
            with factory() as s:
                status = s.scalar(select(SolverRun.Status).where(SolverRun.RunID == run_id))
                cancelled[0] = status == "CANCELLED"
        return cancelled[0]

    return check


def execute_run(db: Session, run_id: int, session_factory: sessionmaker | None = None) -> SolverRun:
    """QUEUED（またはワーカーが取得済みの RUNNING）の実行を同期で処理する。"""
    from app.engine.model_builder import solve_problem  # OR-Tools は計算時にのみ import する

    factory = session_factory or sessionmaker(bind=db.get_bind(), expire_on_commit=False)
    run = db.get(SolverRun, run_id)
    plan = db.get(Plan, run.PlanID)
    run.Status, run.StartedAt = "RUNNING", run.StartedAt or utcnow()
    db.commit()
    try:
        problem = build_problem(db, plan, run.Scope)
        run.TaskCount = len(problem.tasks)
        db.commit()
        result = solve_problem(
            problem, run.TimeLimitSec,
            on_progress=_progress_writer(factory, run_id),
            should_stop=_cancel_checker(factory, run_id),
        )
        db.refresh(run)
        feasible = result.status in ("OPTIMAL", "FEASIBLE")
        if feasible:
            write_results(db, plan, problem, result.assignments, run.RequestedBy)
        run.SolverStatus = result.status
        run.ObjectiveValue, run.BestBound = result.objective, result.bound
        run.ProgressJSON = {
            **(run.ProgressJSON or {}), "wallTime": round(result.wall_time, 2),
            "scheduled": len(result.assignments), "notes": result.notes,
        }
        if run.Status != "CANCELLED":
            run.Status = "SUCCEEDED" if feasible else "FAILED"
        if not feasible:
            run.ErrorMessage = f"Solver status {result.status}. " + "; ".join(result.notes)
    except Exception:
        db.rollback()
        run = db.get(SolverRun, run_id)
        run.Status = "FAILED"
        run.ErrorMessage = traceback.format_exc()[-4000:]
    run.FinishedAt = utcnow()
    db.commit()
    return run

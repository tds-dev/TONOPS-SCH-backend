"""ソルバー実行を 1 件、最後まで処理する: スナップショット → CP-SAT → 結果の書込み。

計画に書き込む結果:
  T_PlanAssignments  置換（ロック行は IsLocked / Source を保持）
  T_PlanKpis         置換
  T_PlanViolations   置換（納期遅れ、未割付タスク、ルール違反）
"""
import time
import traceback
from collections.abc import Callable
from dataclasses import replace

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.timeutil import jst_now
from app.engine.day_evaluate import check_day_schedule, compute_day_kpis
from app.engine.day_problem import DayProblem
from app.engine.day_snapshot import build_day_problem
from app.engine.evaluate import check_schedule, compute_kpis
from app.engine.problem import Problem
from app.engine.result import SAssignment, Violation
from app.engine.snapshot import build_problem
from app.models.masters import CalculationSetting
from app.models.transactions import Plan, PlanAssignment, PlanKpi, PlanViolation, SolverRun

PROGRESS_EVERY_SEC = 1.0
CANCEL_CHECK_EVERY_SEC = 2.0


# 計画に紐づく計算設定から、日単位計算モード（TimeUnit == 'DAY'）か判定する。
def is_day_mode(db: Session, plan: Plan) -> bool:
    setting = db.get(CalculationSetting, plan.CalculationSettingID)
    return bool(setting and setting.TimeUnit == "DAY")


# T_PlanKpis と T_PlanViolations の置換処理を分単位・日単位の両モードで共用する。
def _replace_evaluation(
    db: Session, plan: Plan, kpis: dict[str, float], violations: list[Violation], user: str
) -> None:
    db.execute(delete(PlanKpi).where(PlanKpi.PlanID == plan.PlanID))
    for key, value in kpis.items():
        db.add(PlanKpi(PlanID=plan.PlanID, KpiKey=key, KpiValue=value))

    db.execute(delete(PlanViolation).where(PlanViolation.PlanID == plan.PlanID))
    for v in violations:
        db.add(PlanViolation(
            PlanID=plan.PlanID, TaskID=v.task_id, Severity=v.severity,
            Penalty=v.penalty, Message=v.message[:500], CreatedBy=user,
        ))


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

    write_evaluation(db, plan, problem, assignments, user)


def write_evaluation(db: Session, plan: Plan, problem: Problem, assignments: list[SAssignment], user: str) -> None:
    """KPI と違反を計算し直して T_PlanKpis / T_PlanViolations を置き換える。

    課題一覧にはロック済みの割付も含めてすべての問題を載せる（計画者が非稼働時間に
    置いたロックタスクなども見えるようにする）。
    """
    checked = [replace(a, locked=False) for a in assignments]
    _replace_evaluation(db, plan, compute_kpis(problem, checked), check_schedule(problem, checked), user)


# 日次バケット計算の結果を T_PlanAssignments（WorkerID＋必要に応じてResourceID設定）へ保存し評価を更新する。
def write_day_results(
    db: Session, plan: Plan, problem: DayProblem, assignments: list[SAssignment], user: str
) -> None:
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
            PlanID=plan.PlanID,
            TaskID=a.task_id,
            ResourceID=a.resource_id,
            WorkerID=a.worker_id,
            StartAt=problem.day_to_start_dt(a.start),
            EndAt=problem.day_to_end_dt(a.end),
            SetupMinutes=0,
            IsLocked=locked,
            Source=(prev.Source if locked and prev else "SOLVER"),
            CreatedBy=user,
        ))

    write_day_evaluation(db, plan, problem, assignments, user)


# 日次バケット方式の KPI と違反を再集計して T_PlanKpis / T_PlanViolations を置き換える。
def write_day_evaluation(
    db: Session, plan: Plan, problem: DayProblem, assignments: list[SAssignment], user: str
) -> None:
    checked = [replace(a, locked=False) for a in assignments]
    _replace_evaluation(db, plan, compute_day_kpis(problem, checked), check_day_schedule(problem, checked), user)


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
    from app.engine.day_solver import solve_day_problem  # OR-Tools は計算時にのみ import する
    from app.engine.model_builder import solve_problem

    factory = session_factory or sessionmaker(bind=db.get_bind(), expire_on_commit=False)
    run = db.get(SolverRun, run_id)
    plan = db.get(Plan, run.PlanID)
    run.Status, run.StartAt = "RUNNING", run.StartAt or jst_now()
    db.commit()
    try:
        # 計算設定の時間単位に応じて、日次バケット方式と分単位方式を切り替える。
        day_mode = is_day_mode(db, plan)
        if day_mode:
            day_problem = build_day_problem(db, plan, run.Scope)
            run.TaskCount = len(day_problem.tasks)
            db.commit()
            result = solve_day_problem(
                day_problem,
                on_progress=_progress_writer(factory, run_id),
                should_stop=_cancel_checker(factory, run_id),
            )
            db.refresh(run)
            feasible = result.status in ("OPTIMAL", "FEASIBLE")
            if feasible:
                write_day_results(db, plan, day_problem, result.assignments, run.RequestedBy)
        else:
            problem = build_problem(db, plan, run.Scope)
            run.TaskCount = len(problem.tasks)
            db.commit()
            result = solve_problem(
                problem,
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
    run.EndAt = jst_now()
    db.commit()
    return run

"""Plans, solver runs and their results (Phase 2).

Approve / discard, the board view and manual edits follow in Phase 3.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.engine.rules import all_plugins
from app.engine.solve import execute_run
from app.models.masters import Resource
from app.models.transactions import Job, Plan, PlanAssignment, PlanKpi, PlanViolation, SolverRun, Task
from app.routers.deps import current_user
from app.schemas.base import ApiModel, UtcDatetime, coerce, schemas_for
from app.services.plan_service import create_plan, queue_run

PlanRead, _, _ = schemas_for(Plan)
RunRead, _, _ = schemas_for(SolverRun)
ViolationRead, _, _ = schemas_for(PlanViolation)

router = APIRouter(tags=["Plans"])


class PlanCreateBody(ApiModel):
    site_id: int
    horizon_start: UtcDatetime
    horizon_end: UtcDatetime
    plan_name: str | None = None
    profile_id: int | None = None
    base_plan_id: int | None = None
    use_master_as_base: bool = True
    memo: str | None = None


class SolveBody(ApiModel):
    scope: str = "FULL"  # FULL or REPAIR
    time_limit_sec: int | None = None
    wait: bool = False  # run inside the request (development / tests); otherwise the worker runs it


class AssignmentView(ApiModel):
    assignment_id: int
    task_id: int
    job_id: int
    job_no: str
    task_name: str
    resource_id: int
    resource_code: str
    start_at: UtcDatetime
    end_at: UtcDatetime
    setup_minutes: int
    is_locked: bool
    source: str
    attributes: dict = {}


class RuleTypeView(ApiModel):
    type_key: str
    label: str
    description: str
    supports_soft: bool
    params_schema: dict


def _plan_or_404(db: Session, plan_id: int) -> Plan:
    plan = db.get(Plan, plan_id)
    if plan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Plan {plan_id} not found")
    return plan


@router.get("/plans", response_model=list[PlanRead])
def list_plans(
    site_id: int | None = Query(None, alias="siteId"),
    plan_status: str | None = Query(None, alias="status"),
    db: Session = Depends(get_db),
):
    """Filter with ?siteId=1&status=DRAFT,MASTER."""
    stmt = select(Plan).order_by(Plan.HorizonStart.desc(), Plan.PlanID.desc())
    if site_id is not None:
        stmt = stmt.where(Plan.SiteID == site_id)
    if plan_status:
        stmt = stmt.where(Plan.Status.in_(plan_status.upper().split(",")))
    return db.scalars(stmt).all()


@router.post("/plans", response_model=PlanRead, status_code=status.HTTP_201_CREATED)
def post_plan(body: PlanCreateBody, db: Session = Depends(get_db), user: str = Depends(current_user)):
    return create_plan(db, user=user, **body.model_dump())


@router.get("/plans/{plan_id}", response_model=PlanRead)
def get_plan(plan_id: int, db: Session = Depends(get_db)):
    return _plan_or_404(db, plan_id)


@router.post("/plans/{plan_id}/solve", response_model=RunRead, status_code=status.HTTP_202_ACCEPTED)
def post_solve(
    plan_id: int, body: SolveBody, response: Response,
    db: Session = Depends(get_db), user: str = Depends(current_user),
):
    """Queue a solve. With `wait: true` the solve runs inside the request."""
    if body.scope not in ("FULL", "REPAIR"):
        raise HTTPException(422, "scope must be FULL or REPAIR")
    run = queue_run(db, _plan_or_404(db, plan_id), user, body.scope, body.time_limit_sec)
    if body.wait:
        run = execute_run(db, run.RunID)
        response.status_code = status.HTTP_200_OK
    return run


@router.get("/plans/{plan_id}/solver-runs", response_model=list[RunRead])
def list_runs(plan_id: int, db: Session = Depends(get_db)):
    return db.scalars(select(SolverRun).where(SolverRun.PlanID == plan_id).order_by(SolverRun.RunID.desc())).all()


@router.get("/solver-runs/{run_id}", response_model=RunRead)
def get_run(run_id: int, db: Session = Depends(get_db)):
    run = db.get(SolverRun, run_id)
    if run is None:
        raise HTTPException(404, f"Solver run {run_id} not found")
    return run


@router.post("/solver-runs/{run_id}/cancel", response_model=RunRead)
def cancel_run(run_id: int, db: Session = Depends(get_db)):
    """Queued runs stop at once; running ones stop within a few seconds and keep the best plan found."""
    run = get_run(run_id, db)
    if run.Status in ("QUEUED", "RUNNING"):
        run.Status = "CANCELLED"
        db.commit()
    return run


@router.get("/plans/{plan_id}/assignments", response_model=list[AssignmentView])
def list_assignments(plan_id: int, db: Session = Depends(get_db)):
    _plan_or_404(db, plan_id)
    rows = db.execute(
        select(PlanAssignment, Task, Job, Resource)
        .join(Task, Task.TaskID == PlanAssignment.TaskID)
        .join(Job, Job.JobID == Task.JobID)
        .join(Resource, Resource.ResourceID == PlanAssignment.ResourceID)
        .where(PlanAssignment.PlanID == plan_id)
        .order_by(Resource.SortOrder, PlanAssignment.StartAt)
    ).all()
    return [
        AssignmentView(
            assignment_id=a.AssignmentID, task_id=t.TaskID, job_id=j.JobID, job_no=j.JobNo,
            task_name=t.TaskName, resource_id=r.ResourceID, resource_code=r.ResourceCode,
            start_at=a.StartAt, end_at=a.EndAt, setup_minutes=a.SetupMinutes,
            is_locked=a.IsLocked, source=a.Source, attributes=t.AttributesJSON or {},
        )
        for a, t, j, r in rows
    ]


@router.get("/plans/{plan_id}/kpis", response_model=dict[str, float])
def get_kpis(plan_id: int, db: Session = Depends(get_db)):
    _plan_or_404(db, plan_id)
    return {k.KpiKey: coerce(k.KpiValue) for k in db.scalars(select(PlanKpi).where(PlanKpi.PlanID == plan_id))}


@router.get("/plans/{plan_id}/violations", response_model=list[ViolationRead])
def get_violations(plan_id: int, db: Session = Depends(get_db)):
    _plan_or_404(db, plan_id)
    return db.scalars(
        select(PlanViolation).where(PlanViolation.PlanID == plan_id).order_by(PlanViolation.Severity, PlanViolation.ViolationID)
    ).all()


@router.get("/rule-types", response_model=list[RuleTypeView], tags=["Configuration"])
def list_rule_types():
    """Available rule plugins and the JSON Schema of their parameters (drives the rule editor form)."""
    return [
        RuleTypeView(type_key=p.type_key, label=p.label, description=p.description,
                     supports_soft=p.supports_soft, params_schema=p.params_schema)
        for p in all_plugins()
    ]

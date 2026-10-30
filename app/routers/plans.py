"""計画、ソルバー実行とその結果、計画のライフサイクル（承認・破棄・複製）。

ボード表示・手動編集・比較・配台表は app/routers/board.py。
"""
import time
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import db as dbmod
from app.core.db import get_db
from app.core.timeutil import to_utc_naive
from app.engine.rules import all_plugins
from app.engine.solve import execute_run
from app.models.masters import Resource, Site
from app.models.transactions import Order, Plan, PlanAssignment, PlanKpi, PlanViolation, SolverRun, Task
from app.routers.deps import current_user
from app.schemas.base import ApiModel, UtcDatetime, coerce, schemas_for
from app.services.plan_lifecycle import approve_plan, copy_plan, discard_plan
from app.services.plan_service import create_plan, queue_run

PlanRead, _, _ = schemas_for(Plan)
RunRead, _, _ = schemas_for(SolverRun)
ViolationRead, _, _ = schemas_for(PlanViolation)

router = APIRouter(tags=["Plans"])


class PlanCreateBody(ApiModel):
    site_id: int
    horizon_start: datetime  # オフセットなしは拠点の現地時刻、ありはそのまま UTC に変換
    horizon_end: datetime
    plan_name: str | None = None
    profile_id: int | None = None
    base_plan_id: int | None = None
    use_master_as_base: bool = True
    memo: str | None = None


class SolveBody(ApiModel):
    scope: str = "FULL"  # FULL または REPAIR
    time_limit_sec: int | None = None
    wait: bool = False  # 同期計算を指定した場合はリクエスト内で実行する。通常はワーカーが実行する


class AssignmentView(ApiModel):
    assignment_id: int
    task_id: int
    order_id: int
    order_no: str
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
    """?siteId=1&status=DRAFT,MASTER で絞り込む。"""
    stmt = select(Plan).order_by(Plan.HorizonStart.desc(), Plan.PlanID.desc())
    if site_id is not None:
        stmt = stmt.where(Plan.SiteID == site_id)
    if plan_status:
        stmt = stmt.where(Plan.Status.in_(plan_status.upper().split(",")))
    return db.scalars(stmt).all()


@router.post("/plans", response_model=PlanRead, status_code=status.HTTP_201_CREATED)
def post_plan(body: PlanCreateBody, db: Session = Depends(get_db), user: str = Depends(current_user)):
    site = db.get(Site, body.site_id)
    if site is None:
        raise HTTPException(404, f"拠点 {body.site_id} が見つかりません")
    data = body.model_dump()
    data["horizon_start"] = to_utc_naive(body.horizon_start, site.TimeZone)
    data["horizon_end"] = to_utc_naive(body.horizon_end, site.TimeZone)
    return create_plan(db, user=user, **data)


@router.get("/plans/{plan_id}", response_model=PlanRead)
def get_plan(plan_id: int, db: Session = Depends(get_db)):
    return _plan_or_404(db, plan_id)


@router.post("/plans/{plan_id}/solve", response_model=RunRead, status_code=status.HTTP_202_ACCEPTED)
def post_solve(
    plan_id: int, body: SolveBody, response: Response,
    db: Session = Depends(get_db), user: str = Depends(current_user),
):
    """計算をキューに登録する。`wait: true` の場合はリクエスト内で計算する。"""
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
    """待機中の実行は即座に、実行中のものは数秒以内に停止し、それまでの最良解を残す。"""
    run = get_run(run_id, db)
    if run.Status in ("QUEUED", "RUNNING"):
        run.Status = "CANCELLED"
        db.commit()
    return run


@router.get("/plans/{plan_id}/assignments", response_model=list[AssignmentView])
def list_assignments(plan_id: int, db: Session = Depends(get_db)):
    _plan_or_404(db, plan_id)
    rows = db.execute(
        select(PlanAssignment, Task, Order, Resource)
        .join(Task, Task.TaskID == PlanAssignment.TaskID)
        .join(Order, Order.OrderID == Task.OrderID)
        .join(Resource, Resource.ResourceID == PlanAssignment.ResourceID)
        .where(PlanAssignment.PlanID == plan_id)
        .order_by(Resource.SortOrder, PlanAssignment.StartAt)
    ).all()
    return [
        AssignmentView(
            assignment_id=a.AssignmentID, task_id=t.TaskID, order_id=j.OrderID, order_no=j.OrderNo,
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
    """利用可能なルールプラグインとパラメータの JSON Schema（ルール編集フォームに使う）。"""
    return [
        RuleTypeView(type_key=p.type_key, label=p.label, description=p.description,
                     supports_soft=p.supports_soft, params_schema=p.params_schema)
        for p in all_plugins()
    ]


# ---------------------------------------------------------------- ライフサイクル（フェーズ3）
class ApproveBody(ApiModel):
    force: bool = False  # 必須制約の違反があっても承認する


class CopyBody(ApiModel):
    plan_name: str | None = None


@router.post("/plans/{plan_id}/approve", response_model=PlanRead)
def post_approve(plan_id: int, body: ApproveBody | None = None,
                 db: Session = Depends(get_db), user: str = Depends(current_user)):
    """下書きをマスタにする。重なる既存のマスタは置換済（SUPERSEDED）または破棄（DISCARDED）になる。"""
    return approve_plan(db, _plan_or_404(db, plan_id), user, force=bool(body and body.force))


@router.post("/plans/{plan_id}/discard", response_model=PlanRead)
def post_discard(plan_id: int, db: Session = Depends(get_db), user: str = Depends(current_user)):
    """下書きを破棄する。"""
    return discard_plan(db, _plan_or_404(db, plan_id), user)


@router.post("/plans/{plan_id}/copy", response_model=PlanRead, status_code=status.HTTP_201_CREATED)
def post_copy(plan_id: int, body: CopyBody | None = None,
              db: Session = Depends(get_db), user: str = Depends(current_user)):
    """割付ごと複製した新しい下書きを作る（what-if 用）。"""
    return copy_plan(db, _plan_or_404(db, plan_id), user, body.plan_name if body else None)


@router.get("/solver-runs/{run_id}/events")
def run_events(run_id: int):
    """計算の進捗を Server-Sent Events で送る。完了・失敗・キャンセルで終了する。

    ストリームはリクエストより長く続くため、DB セッションは generator 内で開く。
    """
    def stream():
        last = None
        while True:
            with dbmod.SessionLocal() as s:
                run = s.get(SolverRun, run_id)
                if run is None:
                    yield 'event: error\ndata: {"message": "not found"}\n\n'
                    return
                payload = RunRead.model_validate(run).model_dump_json(by_alias=True)
                done = run.Status in ("SUCCEEDED", "FAILED", "CANCELLED")
            if payload != last:
                yield f"data: {payload}\n\n"
                last = payload
            if done:
                return
            time.sleep(1)

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})

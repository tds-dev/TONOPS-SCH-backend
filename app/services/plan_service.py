"""計画の作成とソルバー実行のキュー登録。"""
from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.timeutil import utc_to_local, utcnow
from app.models.masters import PlanProfile, Site
from app.models.transactions import Plan, SolverRun


def next_plan_no(db: Session, site: Site, horizon_start: datetime) -> str:
    prefix = f"P-{utc_to_local(horizon_start, site.TimeZone):%Y%m%d}-"
    count = db.scalar(
        select(func.count()).select_from(Plan).where(Plan.SiteID == site.SiteID, Plan.PlanNo.like(prefix + "%"))
    )
    return f"{prefix}{(count or 0) + 1:02d}"


def current_master(db: Session, site_id: int, at: datetime) -> Plan | None:
    """`at` を含む MASTER 計画（計画開始が最も遅いものを優先）。"""
    return db.scalars(
        select(Plan)
        .where(Plan.SiteID == site_id, Plan.Status == "MASTER", Plan.HorizonEnd > at)
        .order_by(Plan.HorizonStart.desc())
    ).first()


def create_plan(
    db: Session,
    *,
    site_id: int,
    horizon_start: datetime,
    horizon_end: datetime,
    user: str,
    plan_name: str | None = None,
    profile_id: int | None = None,
    base_plan_id: int | None = None,
    use_master_as_base: bool = True,
    memo: str | None = None,
) -> Plan:
    site = db.get(Site, site_id)
    if site is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Site {site_id} not found")
    if horizon_end <= horizon_start:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "horizonEnd must be after horizonStart")
    if profile_id is None:
        profile = db.scalars(
            select(PlanProfile).where(PlanProfile.SiteID == site_id).order_by(PlanProfile.IsDefault.desc())
        ).first()
        if profile is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "No plan profile for this site")
        profile_id = profile.ProfileID
    if base_plan_id is None and use_master_as_base:
        master = current_master(db, site_id, horizon_start)
        base_plan_id = master.PlanID if master else None
    plan_no = next_plan_no(db, site, horizon_start)
    plan = Plan(
        SiteID=site_id, PlanNo=plan_no, PlanName=plan_name or plan_no, Status="DRAFT",
        HorizonStart=horizon_start, HorizonEnd=horizon_end, ProfileID=profile_id,
        BasePlanID=base_plan_id, Memo=memo, CreatedBy=user,
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


def queue_run(db: Session, plan: Plan, user: str, scope: str = "FULL", time_limit_sec: int | None = None) -> SolverRun:
    if plan.Status != "DRAFT":
        raise HTTPException(status.HTTP_409_CONFLICT, f"Only DRAFT plans can be solved (plan is {plan.Status})")
    busy = db.scalar(
        select(SolverRun.RunID).where(SolverRun.PlanID == plan.PlanID, SolverRun.Status.in_(["QUEUED", "RUNNING"]))
    )
    if busy is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Plan already has an active solver run ({busy})")
    profile = db.get(PlanProfile, plan.ProfileID)
    run = SolverRun(
        PlanID=plan.PlanID, Status="QUEUED", Scope=scope, RequestedBy=user, RequestedAt=utcnow(),
        TimeLimitSec=time_limit_sec or (profile.TimeLimitSec if profile else 60), CreatedBy=user,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run

"""計画の作成とソルバー実行のキュー登録。"""
from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.timeutil import jst_now
from app.models.masters import CalculationSetting, Location
from app.models.transactions import Plan, SolverRun
from app.services.plan_validation import flush_named_plan, validate_plan_name


# 指定時点に対する、開始が最も遅いマスタ計画を取得する。
def current_master(db: Session, location_id: int, at: datetime) -> Plan | None:
    """`at` を含む MASTER 計画（計画開始が最も遅いものを優先）。"""
    return db.scalars(
        select(Plan)
        .where(Plan.LocationID == location_id, Plan.Status == "MASTER", Plan.HorizonEnd > at)
        .order_by(Plan.HorizonStart.desc())
    ).first()


# 指定した拠点の計算条件と元計画を使い、下書き計画を登録する。
def create_plan(
    db: Session,
    *,
    # 取得・作成の対象となる拠点の識別番号。
    location_id: int,
    horizon_start: datetime,
    horizon_end: datetime,
    user: str,
    plan_name: str | None = None,
    calculation_setting_id: int | None = None,
    base_plan_id: int | None = None,
    use_master_as_base: bool = True,
    remarks: str | None = None,
) -> Plan:
    # 対象の拠点が存在することを確認する。
    location = db.get(Location, location_id)
    if location is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Location {location_id} not found")
    if horizon_end <= horizon_start:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "horizonEnd must be after horizonStart")
    # 同じ拠点で重複しない計画名を必須にする。
    name = validate_plan_name(db, location_id, plan_name)
    if calculation_setting_id is None:
        setting = db.scalars(
            select(CalculationSetting).where(CalculationSetting.LocationID == location_id).order_by(CalculationSetting.IsDefault.desc())
        ).first()
        if setting is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "この拠点の計算設定がありません")
        calculation_setting_id = setting.CalculationSettingID
    if base_plan_id is None and use_master_as_base:
        master = current_master(db, location_id, horizon_start)
        base_plan_id = master.PlanID if master else None
    plan = Plan(
        LocationID=location_id, PlanName=name, Status="DRAFT",
        HorizonStart=horizon_start, HorizonEnd=horizon_end, CalculationSettingID=calculation_setting_id,
        BasePlanID=base_plan_id, Remarks=remarks, CreatedBy=user,
    )
    db.add(plan)
    flush_named_plan(db, plan)
    db.commit()
    db.refresh(plan)
    return plan


# 下書き計画の重複実行を確認して、計算の実行要求を登録する。
def queue_run(db: Session, plan: Plan, user: str, scope: str = "FULL", time_limit_sec: int | None = None) -> SolverRun:
    if plan.Status != "DRAFT":
        raise HTTPException(status.HTTP_409_CONFLICT, f"Only DRAFT plans can be solved (plan is {plan.Status})")
    busy = db.scalar(
        select(SolverRun.RunID).where(SolverRun.PlanID == plan.PlanID, SolverRun.Status.in_(["QUEUED", "RUNNING"]))
    )
    if busy is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Plan already has an active solver run ({busy})")
    setting = db.get(CalculationSetting, plan.CalculationSettingID)
    run = SolverRun(
        PlanID=plan.PlanID, Status="QUEUED", Scope=scope, RequestedBy=user, RequestedAt=jst_now(),
        TimeLimitSec=time_limit_sec or (setting.TimeLimitSec if setting else 60), CreatedBy=user,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run

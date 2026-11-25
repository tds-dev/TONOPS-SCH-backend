"""計画の作成とソルバー実行のキュー登録。"""
from datetime import datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.timeutil import jst_now
from app.models.masters import CalculationSetting, Location
from app.models.transactions import Plan, PlanAssignment, PlanViolation, SolverRun
from app.engine.day_snapshot import build_day_problem
from app.engine.result import SAssignment
from app.engine.snapshot import build_problem
from app.engine.solve import is_day_mode, write_day_evaluation, write_evaluation
from app.services.plan_validation import flush_named_plan, validate_plan_name, validate_plan_period, validate_plan_remarks


# 指定時点に対する、開始が最も遅いマスタ計画を取得する。
def current_master(db: Session, location_id: int, at: datetime) -> Plan | None:
    """`at` を含む MASTER 計画（計画開始が最も遅いものを優先）。"""
    return db.scalars(
        select(Plan)
        .where(Plan.LocationID == location_id, Plan.Status == "MASTER", Plan.EndAt > at)
        .order_by(Plan.StartAt.desc())
    ).first()


# 指定した拠点の計算条件と元計画を使い、下書き計画を登録する。
def create_plan(
    db: Session,
    *,
    # 取得・作成の対象となる拠点の識別番号。
    location_id: int,
    start_at: datetime,
    end_at: datetime,
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
    validate_plan_period(start_at, end_at)
    # 同じ拠点で重複しない計画名を必須にする。
    name = validate_plan_name(db, location_id, plan_name)
    remarks = validate_plan_remarks(remarks)
    if calculation_setting_id is None:
        setting = db.scalars(
            select(CalculationSetting).where(
                CalculationSetting.LocationID == location_id,
                CalculationSetting.TimeUnit == location.LocationTimeUnit,
            ).order_by(CalculationSetting.IsDefault.desc())
        ).first()
        if setting is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "この拠点の計算設定がありません")
        calculation_setting_id = setting.CalculationSettingID
    # 明示選択した計算設定も所属拠点を確認し、別拠点の条件で計算することを防ぐ。
    setting = db.get(CalculationSetting, calculation_setting_id)
    if setting is None or setting.LocationID != location_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "同じ拠点の計算設定を指定してください。")
    # 新規計画では画面の表示モードと異なる計算条件を使用しない。
    if setting.TimeUnit != location.LocationTimeUnit:
        raise HTTPException(422, "ロケーションの計算モードと同じ計算設定を指定してください。")
    if base_plan_id is None and use_master_as_base:
        master = current_master(db, location_id, start_at)
        base_plan_id = master.PlanID if master else None
    plan = Plan(
        LocationID=location_id, PlanName=name, Status="DRAFT",
        StartAt=start_at, EndAt=end_at, CalculationSettingID=calculation_setting_id,
        BasePlanID=base_plan_id, Remarks=remarks, CreatedBy=user,
    )
    db.add(plan)
    flush_named_plan(db, plan)
    db.commit()
    db.refresh(plan)
    return plan


# 名前・備考は全状態で、期間・計算設定は下書きだけ更新し、割付の日時と設備を保持する。
def update_plan(db: Session, plan_id: int, values: dict[str, Any], user: str) -> Plan:
    # 同じ計画への同時編集を直列化し、読み込み後の変更をRowVerで検出する。
    plan = db.scalar(select(Plan).where(Plan.PlanID == plan_id)
                     .with_hint(Plan, "WITH (UPDLOCK, HOLDLOCK)", dialect_name="mssql")
                     .execution_options(populate_existing=True))
    if plan is None:
        raise HTTPException(404, "計画が見つかりません。")
    if values["row_ver"] != plan.RowVer:
        raise HTTPException(409, "計画が更新されています。一覧を開き直してから編集してください。")
    condition_keys = {"start_at", "end_at", "calculation_setting_id"}
    if condition_keys.intersection(values) and plan.Status != "DRAFT":
        raise HTTPException(409, "開始日時・終了日時・計算設定は下書きの計画のみ変更できます。")
    # 備考のNULLだけは内容の削除として受け付け、他項目の必須制約を維持する。
    if any(values[key] is None for key in values if key not in {"row_ver", "remarks"}):
        raise HTTPException(422, "更新する項目にnullは指定できません。")
    name = validate_plan_name(db, plan.LocationID, values.get("plan_name", plan.PlanName), plan.PlanID)
    # 未送信の場合は元の備考を保持し、明示された空欄・NULLだけを削除する。
    remarks = validate_plan_remarks(values["remarks"]) if "remarks" in values else plan.Remarks
    start = values.get("start_at", plan.StartAt)
    end = values.get("end_at", plan.EndAt)
    if {"start_at", "end_at"}.intersection(values):
        validate_plan_period(start, end)
    setting_id = values.get("calculation_setting_id", plan.CalculationSettingID)
    # 保存済み設定が別拠点のものへ差し替わらないよう確認する。
    if "calculation_setting_id" in values:
        setting = db.get(CalculationSetting, setting_id)
        if setting is None or setting.LocationID != plan.LocationID:
            raise HTTPException(422, "同じ拠点の計算設定を指定してください。")
        # 計算設定の変更時も新規作成と同じモード制約を守る。
        location = db.get(Location, plan.LocationID)
        if setting.TimeUnit != location.LocationTimeUnit:
            raise HTTPException(422, "ロケーションの計算モードと同じ計算設定を指定してください。")
    conditions_changed = (start, end, setting_id) != (plan.StartAt, plan.EndAt, plan.CalculationSettingID)
    if conditions_changed and db.scalar(select(SolverRun.RunID).where(
        SolverRun.PlanID == plan.PlanID, SolverRun.Status.in_(["QUEUED", "RUNNING"]),
    )) is not None:
        raise HTTPException(409, "計算の待機中・実行中は計画条件を変更できません。")
    try:
        plan.PlanName = name
        plan.Remarks = remarks
        plan.StartAt, plan.EndAt, plan.CalculationSettingID = start, end, setting_id
        plan.UpdatedBy = user
        flush_named_plan(db, plan)
        if conditions_changed:
            # 割付そのものは移動・削除せず、新しい開始日時・計算設定を基準に評価だけを更新する。
            rows = db.scalars(select(PlanAssignment).where(PlanAssignment.PlanID == plan.PlanID)).all()
            if is_day_mode(db, plan):
                day_problem = build_day_problem(db, plan)
                day_assignments: list[SAssignment] = []
                for row in rows:
                    s_day = day_problem.dt_to_day_idx(row.StartAt)
                    e_day = day_problem.end_dt_to_day_idx(row.EndAt)
                    if s_day is not None and e_day is not None:
                        day_assignments.append(SAssignment(
                            row.TaskID, None, s_day, e_day, 0, row.IsLocked, worker_id=row.WorkerID
                        ))
                write_day_evaluation(db, plan, day_problem, day_assignments, user)
            else:
                assignments = [SAssignment(
                    row.TaskID, row.ResourceID,
                    int((row.StartAt - start).total_seconds() // 60),
                    int((row.EndAt - start).total_seconds() // 60), row.SetupMinutes, row.IsLocked,
                ) for row in rows if row.ResourceID is not None]
                write_evaluation(db, plan, build_problem(db, plan), assignments, user)
            db.add(PlanViolation(
                PlanID=plan.PlanID, Severity="INFO", CreatedBy=user,
                Message="計画条件を変更しました。既存の割付は保持しています。計画ボードで再計算してください。",
            ))
        db.commit()
        db.refresh(plan)
        return plan
    except Exception:
        db.rollback()
        raise


# 下書き計画の重複実行を確認して、計算の実行要求を登録する。
def queue_run(db: Session, plan: Plan, user: str, scope: str = "FULL") -> SolverRun:
    if plan.Status != "DRAFT":
        raise HTTPException(status.HTTP_409_CONFLICT, f"Only DRAFT plans can be solved (plan is {plan.Status})")
    busy = db.scalar(
        select(SolverRun.RunID).where(SolverRun.PlanID == plan.PlanID, SolverRun.Status.in_(["QUEUED", "RUNNING"]))
    )
    if busy is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Plan already has an active solver run ({busy})")
    run = SolverRun(
        PlanID=plan.PlanID, Status="QUEUED", Scope=scope, RequestedBy=user, RequestedAt=jst_now(),
        CreatedBy=user,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run

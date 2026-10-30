"""計画のライフサイクル: 承認・破棄・複製と、マスタ計画の割付の取得。

状態遷移（提案資料の版管理に準拠）:
  DRAFT ──承認──▶ MASTER
  DRAFT ──破棄──▶ DISCARDED
  MASTER ──新しい MASTER が重なる──▶ SUPERSEDED（新計画の開始より前に始まっていた場合。
          SupersededAt = 新計画の開始。それ以前の割付は引き続き有効）
                                   ▶ DISCARDED（新計画の開始以降に始まる場合。全面置換）

同一拠点で同じ時点を覆う MASTER は常に 1 つ。承認は拠点行をロックした
1 トランザクションで行う（同時承認を防ぐ）。
"""
from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.timeutil import utcnow
from app.models.masters import Site
from app.models.transactions import Order, Plan, PlanAssignment, PlanKpi, PlanViolation, SolverRun, Task
from app.services.plan_service import next_plan_no

# 承認を妨げない必須違反（未割付は「計画に入らなかった」だけで、計画自体は実行可能）
NON_BLOCKING_HARD = {"UNSCHEDULED"}


def _require_draft(plan: Plan) -> None:
    if plan.Status != "DRAFT":
        raise HTTPException(status.HTTP_409_CONFLICT, f"下書きの計画のみ操作できます（現在: {plan.Status}）")


def _active_run(db: Session, plan_id: int) -> int | None:
    return db.scalar(
        select(SolverRun.RunID).where(SolverRun.PlanID == plan_id, SolverRun.Status.in_(["QUEUED", "RUNNING"]))
    )


def approve_plan(db: Session, plan: Plan, user: str, force: bool = False) -> Plan:
    _require_draft(plan)
    if _active_run(db, plan.PlanID):
        raise HTTPException(status.HTTP_409_CONFLICT, "計算中の計画は承認できません")
    n_assign = db.scalar(select(func.count()).select_from(PlanAssignment).where(PlanAssignment.PlanID == plan.PlanID))
    if not n_assign:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "割付のない計画は承認できません")
    blocking = db.scalars(
        select(PlanViolation).where(
            PlanViolation.PlanID == plan.PlanID,
            PlanViolation.Severity == "HARD",
            PlanViolation.ViolationCode.notin_(NON_BLOCKING_HARD),
        )
    ).all()
    if blocking and not force:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            {"message": f"必須制約の違反が {len(blocking)} 件あります。force=true で承認できます",
             "violations": [v.Message for v in blocking[:20]]},
        )

    # 拠点行をロック（SQL Server では UPDLOCK）して、同じ拠点の同時承認を直列化する
    db.execute(select(Site).where(Site.SiteID == plan.SiteID).with_for_update())

    overlapping = db.scalars(
        select(Plan).where(
            Plan.SiteID == plan.SiteID,
            Plan.PlanID != plan.PlanID,
            Plan.Status == "MASTER",
            Plan.HorizonStart < plan.HorizonEnd,
            Plan.HorizonEnd > plan.HorizonStart,
        )
    ).all()
    for other in overlapping:
        if other.HorizonStart < plan.HorizonStart:
            other.Status, other.SupersededAt = "SUPERSEDED", plan.HorizonStart
        else:
            other.Status = "DISCARDED"
        other.UpdatedBy = user
    # 既に SUPERSEDED の計画も、新計画の開始以降は無効にする
    for old in db.scalars(
        select(Plan).where(
            Plan.SiteID == plan.SiteID, Plan.Status == "SUPERSEDED",
            Plan.SupersededAt > plan.HorizonStart, Plan.HorizonStart < plan.HorizonStart,
        )
    ):
        old.SupersededAt = plan.HorizonStart

    plan.Status, plan.ApprovedAt, plan.ApprovedBy, plan.UpdatedBy = "MASTER", utcnow(), user, user
    order_ids = select(Task.OrderID).join(PlanAssignment, PlanAssignment.TaskID == Task.TaskID).where(
        PlanAssignment.PlanID == plan.PlanID
    )
    db.execute(
        update(Order).where(Order.OrderID.in_(order_ids), Order.Status == "OPEN").values(Status="PLANNED", UpdatedBy=user)
    )
    db.commit()
    db.refresh(plan)
    return plan


def discard_plan(db: Session, plan: Plan, user: str) -> Plan:
    _require_draft(plan)
    if _active_run(db, plan.PlanID):
        raise HTTPException(status.HTTP_409_CONFLICT, "計算中の計画は破棄できません。先にキャンセルしてください")
    plan.Status, plan.UpdatedBy = "DISCARDED", user
    db.commit()
    db.refresh(plan)
    return plan


def copy_plan(db: Session, plan: Plan, user: str, name: str | None = None) -> Plan:
    """割付・KPI・違反ごと複製した新しい下書きを作る（what-if 用）。"""
    site = db.get(Site, plan.SiteID)
    new = Plan(
        SiteID=plan.SiteID, PlanNo=next_plan_no(db, site, plan.HorizonStart),
        PlanName=name or f"{plan.PlanName}（コピー）", Status="DRAFT",
        HorizonStart=plan.HorizonStart, HorizonEnd=plan.HorizonEnd, ProfileID=plan.ProfileID,
        BasePlanID=plan.BasePlanID, Memo=plan.Memo, CreatedBy=user,
    )
    db.add(new)
    db.flush()
    for a in db.scalars(select(PlanAssignment).where(PlanAssignment.PlanID == plan.PlanID)):
        db.add(PlanAssignment(
            PlanID=new.PlanID, TaskID=a.TaskID, ResourceID=a.ResourceID, StartAt=a.StartAt, EndAt=a.EndAt,
            SetupMinutes=a.SetupMinutes, Units=a.Units, IsLocked=a.IsLocked, Source=a.Source, CreatedBy=user,
        ))
    for k in db.scalars(select(PlanKpi).where(PlanKpi.PlanID == plan.PlanID)):
        db.add(PlanKpi(PlanID=new.PlanID, KpiKey=k.KpiKey, KpiValue=k.KpiValue))
    for v in db.scalars(select(PlanViolation).where(PlanViolation.PlanID == plan.PlanID)):
        db.add(PlanViolation(
            PlanID=new.PlanID, RuleID=v.RuleID, TaskID=v.TaskID, Severity=v.Severity,
            ViolationCode=v.ViolationCode, Penalty=v.Penalty, Message=v.Message, CreatedBy=user,
        ))
    db.commit()
    db.refresh(new)
    return new


def master_assignments(db: Session, site_id: int, start: datetime, end: datetime) -> list[PlanAssignment]:
    """[start, end) に重なるマスタ計画の割付。

    MASTER の割付と、SUPERSEDED の計画のうち SupersededAt より前に始まる割付を合わせる。
    同じタスクが両方にある場合は MASTER を優先する。
    """
    plans = db.scalars(
        select(Plan).where(
            Plan.SiteID == site_id, Plan.Status.in_(["MASTER", "SUPERSEDED"]),
            Plan.HorizonStart < end, Plan.HorizonEnd > start,
        )
    ).all()
    chosen: dict[int, tuple[bool, PlanAssignment]] = {}
    for p in plans:
        stmt = select(PlanAssignment).where(
            PlanAssignment.PlanID == p.PlanID, PlanAssignment.StartAt < end, PlanAssignment.EndAt > start
        )
        if p.Status == "SUPERSEDED":
            if p.SupersededAt is None:
                continue
            stmt = stmt.where(PlanAssignment.StartAt < p.SupersededAt)
        is_master = p.Status == "MASTER"
        for a in db.scalars(stmt):
            prev = chosen.get(a.TaskID)
            if prev is None or (is_master and not prev[0]):
                chosen[a.TaskID] = (is_master, a)
    return sorted((a for _, a in chosen.values()), key=lambda a: (a.ResourceID, a.StartAt))

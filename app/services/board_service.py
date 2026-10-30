"""計画ボード用のデータ（DayPilot Scheduler 向けに整形）。

時刻はすべて拠点の現地時刻（オフセットなしの ISO 文字列）で返す。DayPilot は
タイムゾーンを持たない日時で描画するため、変換はサーバー側で行う。
"""
from datetime import datetime

from sqlalchemy import false, select, true
from sqlalchemy.orm import Session

from app.core.timeutil import to_utc_naive, utc_to_local
from app.engine.snapshot import build_problem
from app.models.masters import ChangeoverMatrix, Item, Resource, ResourceGroup, Site
from app.models.transactions import Order, Plan, PlanAssignment, PlanKpi, PlanViolation, Task
from app.schemas.base import coerce
from app.services.worktime import gaps

SEVERITY_ORDER = {"HARD": 0, "SOFT": 1, "INFO": 2}


def _local(dt: datetime, tz: str) -> str:
    return utc_to_local(dt, tz).replace(tzinfo=None).isoformat(timespec="seconds")


def default_color_attribute(db: Session, site_id: int) -> str | None:
    """色分けの既定属性: 拠点の有効な段取り替えマトリクスの属性（段取りの単位なので見分けたい）。"""
    return db.scalar(
        select(ChangeoverMatrix.AttributeKey)
        .where(ChangeoverMatrix.SiteID == site_id, ChangeoverMatrix.IsActive == true())
        .order_by(ChangeoverMatrix.MatrixID)
    )


def build_board(
    db: Session,
    plan: Plan,
    start: datetime | None = None,
    end: datetime | None = None,
    resource_group_id: int | None = None,
    color_by: str | None = None,
) -> dict:
    site = db.get(Site, plan.SiteID)
    tz = site.TimeZone
    start = to_utc_naive(start, tz) if start else plan.HorizonStart
    end = to_utc_naive(end, tz) if end else plan.HorizonEnd
    color_by = color_by or default_color_attribute(db, site.SiteID)
    problem = build_problem(db, plan)

    # ---- リソース（グループ順・表示順）
    groups = {g.ResourceGroupID: g for g in db.scalars(select(ResourceGroup).where(ResourceGroup.SiteID == site.SiteID))}
    res_rows = db.scalars(
        select(Resource).where(Resource.SiteID == site.SiteID, Resource.DeleteFlag == false())
    ).all()
    if resource_group_id is not None:
        res_rows = [r for r in res_rows if r.ResourceGroupID == resource_group_id]
    res_rows.sort(key=lambda r: (groups[r.ResourceGroupID].SortOrder if r.ResourceGroupID in groups else 9999,
                                 r.SortOrder, r.ResourceCode))
    resource_ids = {r.ResourceID for r in res_rows}
    resources = [
        {
            "id": r.ResourceID, "code": r.ResourceCode, "name": r.ResourceName, "type": r.ResourceType,
            "capacity": coerce(r.Capacity), "groupId": r.ResourceGroupID,
            "groupName": groups[r.ResourceGroupID].GroupName if r.ResourceGroupID in groups else None,
        }
        for r in res_rows
    ]
    group_list = []
    for r in resources:
        if not group_list or group_list[-1]["id"] != r["groupId"]:
            group_list.append({"id": r["groupId"], "name": r["groupName"], "resourceIds": []})
        group_list[-1]["resourceIds"].append(r["id"])

    # ---- 課題（タスク別の最も重い違反）
    issues = db.scalars(select(PlanViolation).where(PlanViolation.PlanID == plan.PlanID)).all()
    worst: dict[int, str] = {}
    for v in issues:
        if v.TaskID is not None and SEVERITY_ORDER[v.Severity] < SEVERITY_ORDER.get(worst.get(v.TaskID, "INFO"), 3):
            worst[v.TaskID] = v.Severity

    # ---- イベント（割付）と段取りブロック
    rows = db.execute(
        select(PlanAssignment, Task, Order, Item)
        .join(Task, Task.TaskID == PlanAssignment.TaskID)
        .join(Order, Order.OrderID == Task.OrderID)
        .outerjoin(Item, Item.ItemID == Order.ItemID)
        .where(PlanAssignment.PlanID == plan.PlanID, PlanAssignment.StartAt < end, PlanAssignment.EndAt > start)
        .order_by(PlanAssignment.ResourceID, PlanAssignment.StartAt)
    ).all()
    events, setups = [], []
    for a, t, j, item in rows:
        if a.ResourceID not in resource_ids:
            continue
        attrs = t.AttributesJSON or {}
        events.append({
            "id": a.AssignmentID, "resource": a.ResourceID,
            "start": _local(a.StartAt, tz), "end": _local(a.EndAt, tz),
            "text": f"{j.OrderNo} {t.TaskName}",
            "taskId": t.TaskID, "orderId": j.OrderID, "orderNo": j.OrderNo, "taskName": t.TaskName,
            "itemCode": item.ItemCode if item else None, "itemName": item.ItemName if item else None,
            "quantity": coerce(j.Quantity), "unit": item.Unit if item else None,
            "dueAt": _local(j.DueAt, tz) if j.DueAt else None,
            "isLocked": a.IsLocked, "source": a.Source, "setupMinutes": a.SetupMinutes,
            "colorValue": attrs.get(color_by) if color_by else j.OrderNo,
            "issue": worst.get(t.TaskID), "rowVer": a.RowVer,
        })
        if a.SetupMinutes:
            setups.append({
                "id": f"setup-{a.AssignmentID}", "resource": a.ResourceID,
                "start": _local(problem.to_dt(problem.to_min(a.StartAt) - a.SetupMinutes), tz),
                "end": _local(a.StartAt, tz), "minutes": a.SetupMinutes,
            })

    # ---- 非稼働時間（セルの網掛け用）
    non_working = []
    lo, hi = problem.to_min(start), problem.to_min(end)
    for rid in resource_ids:
        pr = problem.resources.get(rid)
        if pr is None:
            continue
        for s, e in gaps(pr.windows, problem.horizon):
            s, e = max(s, lo), min(e, hi)
            if e > s:
                non_working.append({"resource": rid, "start": _local(problem.to_dt(s), tz), "end": _local(problem.to_dt(e), tz)})

    # ---- 未割付タスク（ボードへドラッグして配置できる）
    assigned = set(db.scalars(select(PlanAssignment.TaskID).where(PlanAssignment.PlanID == plan.PlanID)))
    unscheduled = [
        {
            "taskId": t.id, "orderId": t.order_id, "orderNo": problem.orders[t.order_id].no, "name": t.name,
            "durations": {str(o.resource_id): o.duration for o in t.options},
            "dueAt": _local(problem.to_dt(problem.orders[t.order_id].due), tz) if problem.orders[t.order_id].due is not None else None,
            "colorValue": t.attrs.get(color_by) if color_by else None,
        }
        for t in problem.tasks.values() if t.id not in assigned
    ]

    kpis = {k.KpiKey: coerce(k.KpiValue) for k in db.scalars(select(PlanKpi).where(PlanKpi.PlanID == plan.PlanID))}
    return {
        "plan": {
            "planId": plan.PlanID, "planNo": plan.PlanNo, "planName": plan.PlanName, "status": plan.Status,
            "horizonStart": _local(plan.HorizonStart, tz), "horizonEnd": _local(plan.HorizonEnd, tz),
            "rowVer": plan.RowVer,
        },
        "timeZone": tz,
        "from": _local(start, tz),
        "to": _local(end, tz),
        "colorBy": color_by,
        "groups": group_list,
        "resources": resources,
        "events": events,
        "setups": setups,
        "nonWorking": non_working,
        "unscheduled": unscheduled,
        "issues": [
            {"severity": v.Severity, "code": v.ViolationCode, "message": v.Message, "taskId": v.TaskID, "ruleId": v.RuleID}
            for v in sorted(issues, key=lambda v: (SEVERITY_ORDER[v.Severity], v.ViolationID))
        ],
        "kpis": kpis,
    }

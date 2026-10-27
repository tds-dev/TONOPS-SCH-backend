"""計画比較（KPI 差分と差異のあるタスク）と配台表。"""
from datetime import date, datetime, time, timedelta

from fastapi import HTTPException
from sqlalchemy import false, select
from sqlalchemy.orm import Session

from app.core.db import chunks
from app.core.timeutil import to_utc_naive, utc_to_local
from app.engine.compare import Slot, assignment_diff, kpi_deltas
from app.models.masters import Item, Resource, ResourceGroup, Site
from app.models.transactions import Job, Plan, PlanAssignment, PlanKpi, Task
from app.schemas.base import coerce
from app.services.plan_lifecycle import master_assignments

KIND_LABEL = {"MOVED": "時刻変更", "RESOURCE": "設備変更", "ADDED": "追加", "REMOVED": "割付解除"}


def _hhmm(dt: datetime, tz: str) -> str:
    return utc_to_local(dt, tz).strftime("%m/%d %H:%M")


def _shift_text(kind: str, minutes: int | None) -> str:
    if minutes is None or minutes == 0:
        return KIND_LABEL[kind]
    h, m = divmod(abs(minutes), 60)
    span = f"{h}時間{m:02d}分" if h else f"{m}分"
    return f"{span}{'後ろ倒し' if minutes > 0 else '前倒し'}" + ("・設備変更" if kind == "RESOURCE" else "")


def compare_plans(db: Session, a_id: int, b_id: int) -> dict:
    plan_a, plan_b = db.get(Plan, a_id), db.get(Plan, b_id)
    if plan_a is None or plan_b is None:
        raise HTTPException(404, "計画が見つかりません")
    tz = db.get(Site, plan_a.SiteID).TimeZone

    def kpis(pid):
        return {k.KpiKey: coerce(k.KpiValue) for k in db.scalars(select(PlanKpi).where(PlanKpi.PlanID == pid))}

    def slots(pid):
        return {
            a.TaskID: Slot(a.ResourceID, a.StartAt, a.EndAt)
            for a in db.scalars(select(PlanAssignment).where(PlanAssignment.PlanID == pid))
        }

    sa, sb = slots(a_id), slots(b_id)
    changes = assignment_diff(sa, sb)
    task_ids = {c.task_id for c in changes}
    info = {
        t.TaskID: (j.JobNo, t.TaskName)
        for ids in chunks(task_ids)
        for t, j in db.execute(select(Task, Job).join(Job, Job.JobID == Task.JobID).where(Task.TaskID.in_(ids)))
    }
    res = {r.ResourceID: r for r in db.scalars(select(Resource).where(Resource.SiteID == plan_a.SiteID))}

    def slot_view(s: Slot | None):
        if s is None:
            return None
        r = res.get(s.resource_id)
        return {"resourceId": s.resource_id, "resourceName": r.ResourceName if r else str(s.resource_id),
                "start": _hhmm(s.start, tz), "end": _hhmm(s.end, tz)}

    def summary(p: Plan):
        return {"planId": p.PlanID, "planNo": p.PlanNo, "planName": p.PlanName, "status": p.Status,
                "horizonStart": _hhmm(p.HorizonStart, tz), "horizonEnd": _hhmm(p.HorizonEnd, tz)}

    return {
        "a": summary(plan_a),
        "b": summary(plan_b),
        "kpis": [
            {"key": d.key, "label": d.label, "unit": d.unit, "a": d.a, "b": d.b, "delta": d.delta, "better": d.better}
            for d in kpi_deltas(kpis(a_id), kpis(b_id))
        ],
        "changedCount": len(changes),
        "totalTasks": len(set(sa) | set(sb)),
        "changes": [
            {
                "taskId": c.task_id, "jobNo": info.get(c.task_id, ("", ""))[0], "taskName": info.get(c.task_id, ("", ""))[1],
                "kind": c.kind, "shiftMinutes": c.shift_minutes, "description": _shift_text(c.kind, c.shift_minutes),
                "a": slot_view(c.a), "b": slot_view(c.b),
            }
            for c in changes
        ],
    }


def dispatch_list(db: Session, site_id: int, day: date, resource_group_id: int | None = None) -> dict:
    """マスタ計画の配台表（指定日の現地 0:00〜24:00、リソース別・開始順）。"""
    site = db.get(Site, site_id)
    if site is None:
        raise HTTPException(404, f"拠点 {site_id} が見つかりません")
    tz = site.TimeZone
    start = to_utc_naive(datetime.combine(day, time()), tz)
    end = to_utc_naive(datetime.combine(day + timedelta(days=1), time()), tz)
    rows = master_assignments(db, site_id, start, end)
    task_ids = [a.TaskID for a in rows]
    detail = {
        t.TaskID: (t, j, item)
        for ids in chunks(task_ids)
        for t, j, item in db.execute(
            select(Task, Job, Item).join(Job, Job.JobID == Task.JobID).outerjoin(Item, Item.ItemID == Job.ItemID)
            .where(Task.TaskID.in_(ids))
        )
    }
    groups = {g.ResourceGroupID: g for g in db.scalars(select(ResourceGroup).where(ResourceGroup.SiteID == site_id))}
    resources = [
        r for r in db.scalars(select(Resource).where(Resource.SiteID == site_id, Resource.DeleteFlag == false()))
        if resource_group_id is None or r.ResourceGroupID == resource_group_id
    ]
    resources.sort(key=lambda r: (groups[r.ResourceGroupID].SortOrder if r.ResourceGroupID in groups else 9999, r.SortOrder))
    out = []
    for r in resources:
        items = []
        for a in (x for x in rows if x.ResourceID == r.ResourceID):
            t, j, item = detail[a.TaskID]
            items.append({
                "assignmentId": a.AssignmentID, "taskId": t.TaskID, "jobNo": j.JobNo, "taskName": t.TaskName,
                "itemCode": item.ItemCode if item else None, "itemName": item.ItemName if item else None,
                "quantity": coerce(j.Quantity), "unit": item.Unit if item else None,
                "start": utc_to_local(a.StartAt, tz).strftime("%H:%M"),
                "end": utc_to_local(a.EndAt, tz).strftime("%H:%M"),
                "startAt": a.StartAt.isoformat() + "Z", "endAt": a.EndAt.isoformat() + "Z",
                "setupMinutes": a.SetupMinutes, "isLocked": a.IsLocked, "taskStatus": t.Status,
                "attributes": t.AttributesJSON or {},
            })
        out.append({
            "resourceId": r.ResourceID, "resourceCode": r.ResourceCode, "resourceName": r.ResourceName,
            "groupName": groups[r.ResourceGroupID].GroupName if r.ResourceGroupID in groups else None,
            "items": items,
        })
    return {"siteId": site_id, "date": day.isoformat(), "timeZone": tz, "resources": out}

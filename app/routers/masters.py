"""マスタデータのエンドポイント: 汎用ファクトリによる CRUD と、
カレンダーの稼働時間展開。"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.timeutil import to_utc_naive
from app.models import masters as m
from app.routers.crud import crud_router
from app.schemas.base import ApiModel, UtcDatetime
from app.services.calendar_service import working_time

routers = [
    crud_router(m.Organization, "/organizations", "Organizations"),
    crud_router(m.Location, "/locations", "Locations"),
    crud_router(m.Calendar, "/calendars", "Calendars"),
    crud_router(m.CalendarPattern, "/calendar-patterns", "Calendars", order_by="DayOfWeek"),
    crud_router(m.CalendarException, "/calendar-exceptions", "Calendars", order_by="StartAt"),
    crud_router(m.ResourceGroup, "/resource-groups", "Resources", order_by="SortOrder"),
    crud_router(m.Resource, "/resources", "Resources", order_by="SortOrder"),
    crud_router(m.AttributeDefinition, "/attribute-definitions", "Configuration"),
    crud_router(m.Rule, "/rules", "Configuration"),
    crud_router(m.ChangeoverMatrix, "/changeover-matrices", "Configuration"),
    crud_router(m.ChangeoverEntry, "/changeover-entries", "Configuration"),
    crud_router(m.PlanProfile, "/plan-profiles", "Configuration"),
    crud_router(m.Item, "/items", "Items & routings"),
    crud_router(m.Routing, "/routings", "Items & routings"),
    crud_router(m.RoutingStep, "/routing-steps", "Items & routings", order_by="StepNo"),
    crud_router(m.RoutingStepResource, "/routing-step-resources", "Items & routings"),
]


# カレンダーから求めた稼働時間の開始と終了。
class WorkingInterval(ApiModel):
    start: UtcDatetime
    end: UtcDatetime


calendar_extra = APIRouter(prefix="/calendars", tags=["Calendars"])


@calendar_extra.get("/{calendar_id}/working-time", response_model=list[WorkingInterval])
def get_working_time(
    calendar_id: int,
    start: datetime = Query(..., alias="from"),
    end: datetime = Query(..., alias="to"),
    db: Session = Depends(get_db),
):
    """展開した稼働時間（UTC）。ボード上の非稼働時間の網掛けに使う。"""
    cal = db.get(m.Calendar, calendar_id)
    if cal is None:
        raise HTTPException(404, f"Calendar {calendar_id} not found")
    # 対象の拠点情報。現地時刻や既定設定の参照に使う。
    location = db.get(m.Location, cal.LocationID)
    tz = location.TimeZone if location else "UTC"
    s, e = to_utc_naive(start), to_utc_naive(end)
    if e <= s:
        raise HTTPException(422, "'to' must be after 'from'")
    return [WorkingInterval(start=a, end=b) for a, b in working_time(db, calendar_id, s, e, tz)]


routers.append(calendar_extra)

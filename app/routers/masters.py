"""マスタデータのエンドポイント: 汎用ファクトリによる CRUD と、
カレンダーの稼働時間展開。"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.timeutil import to_jst_naive
from app.models import masters as m
from app.routers.crud import crud_router
from app.schemas.base import ApiModel, JstDatetime
from app.services.calendar_service import (
    delete_calendar,
    filter_calendar_exceptions,
    save_calendar,
    validate_calendar_exception_write,
    validate_location_write,
    validate_resource_location_write,
    working_time,
)
from app.services.product_process_service import delete_product_process, save_product_process
from app.services.product_validation import (
    validate_product_process_resource_write,
    validate_product_write,
)

routers = [
    crud_router(m.Location, "/locations", "Locations", validate_write=validate_location_write),
    crud_router(m.Calendar, "/calendars", "Calendars", order_by="DayOfWeek",
                write_handler=save_calendar, delete_handler=delete_calendar),
    crud_router(m.CalendarException, "/calendar-exceptions", "Calendars", order_by="StartAt",
                validate_write=validate_calendar_exception_write, filter_list=filter_calendar_exceptions),
    crud_router(m.ResourceGroup, "/resource-groups", "Resources", order_by="SortOrder"),
    crud_router(m.Resource, "/resources", "Resources", order_by="SortOrder", validate_write=validate_resource_location_write),
    crud_router(m.AttributeDefinition, "/attribute-definitions", "Configuration"),
    crud_router(m.Rule, "/rules", "Configuration"),
    crud_router(m.ProductSwitchTime, "/product-switch-times", "Configuration"),
    crud_router(m.ProductSwitchRule, "/product-switch-rules", "Configuration"),
    crud_router(m.CalculationSetting, "/calculation-settings", "Configuration"),
    crud_router(m.Product, "/products", "Products & processes", validate_write=validate_product_write),
    crud_router(m.ProductProcess, "/product-processes", "Products & processes", order_by="SequenceNumber",
                write_handler=save_product_process, delete_handler=delete_product_process),
    crud_router(m.ProductProcessResource, "/product-process-resources", "Products & processes", validate_write=validate_product_process_resource_write),
]


# カレンダーから求めた稼働時間の開始と終了。
class WorkingInterval(ApiModel):
    start: JstDatetime
    end: JstDatetime


calendar_extra = APIRouter(prefix="/calendars", tags=["Calendars"])


@calendar_extra.get("/{calendar_id}/working-time", response_model=list[WorkingInterval])
def get_working_time(
    calendar_id: int,
    start: datetime = Query(..., alias="from"),
    end: datetime = Query(..., alias="to"),
    db: Session = Depends(get_db),
):
    """展開した稼働時間（日本時間）。ボード上の非稼働時間の網掛けに使う。"""
    cal = db.get(m.Calendar, calendar_id)
    if cal is None or cal.DeleteFlag:
        raise HTTPException(404, f"Calendar {calendar_id} not found")
    # 拠点の時差列を持たず、アプリ共通の日本時間で稼働枠を展開する。
    tz = get_settings().app_timezone
    s, e = to_jst_naive(start), to_jst_naive(end)
    if e <= s:
        raise HTTPException(422, "'to' must be after 'from'")
    return [WorkingInterval(start=a, end=b) for a, b in working_time(db, calendar_id, s, e, tz)]


routers.append(calendar_extra)

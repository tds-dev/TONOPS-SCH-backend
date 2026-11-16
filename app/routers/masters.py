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
    save_calendar,
    validate_calendar_exception_write,
    validate_resource_location_write,
    working_time,
)
from app.services.product_process_service import delete_product_process, save_product_process
from app.services.product_switch_service import filter_product_process_list, validate_switch_rule, validate_switch_time
from app.services.product_validation import (
    validate_product_process_resource_write,
    validate_product_write,
)

# マスタごとの保存・削除時の確認処理をAPIへ登録する。
routers = [
    crud_router(m.Location, "/locations", "Locations"),
    crud_router(m.Calendar, "/calendars", "Calendars", order_by="DayOfWeek",
                write_handler=save_calendar, delete_handler=delete_calendar),
    crud_router(m.CalendarException, "/calendar-exceptions", "Calendars", order_by="StartAt",
                validate_write=validate_calendar_exception_write),
    crud_router(m.ResourceGroup, "/resource-groups", "Resources", order_by="SortOrder"),
    crud_router(m.Resource, "/resources", "Resources", order_by="SortOrder", validate_write=validate_resource_location_write),
    crud_router(m.ProductSwitchTime, "/product-switch-times", "Configuration", validate_write=validate_switch_time),
    crud_router(m.ProductSwitchRule, "/product-switch-rules", "Configuration", validate_write=validate_switch_rule),
    crud_router(m.CalculationSetting, "/calculation-settings", "Configuration"),
    crud_router(m.Product, "/products", "Products & processes", validate_write=validate_product_write),
    crud_router(m.ProductProcess, "/product-processes", "Products & processes", order_by="SequenceNumber",
                write_handler=save_product_process, delete_handler=delete_product_process, filter_list=filter_product_process_list),
    crud_router(m.ProductProcessResource, "/product-process-resources", "Products & processes", validate_write=validate_product_process_resource_write),
]


# カレンダーから求めた稼働時間の開始と終了。
class WorkingInterval(ApiModel):
    start: JstDatetime
    end: JstDatetime


# 勤務行の番号を使わず、拠点の番号から稼働時間を取得する追加API。
calendar_extra = APIRouter(prefix="/locations", tags=["Calendars"])


# 存在する拠点の週間勤務と停止予定を指定期間へ展開する。
@calendar_extra.get("/{location_id}/working-time", response_model=list[WorkingInterval])
def get_working_time(
    location_id: int,
    start: datetime = Query(..., alias="from"),
    end: datetime = Query(..., alias="to"),
    db: Session = Depends(get_db),
):
    """展開した稼働時間（日本時間）。ボード上の非稼働時間の網掛けに使う。"""
    # 削除済み拠点や存在しない番号を、勤務未登録の拠点として扱わない。
    location = db.get(m.Location, location_id)
    if location is None or location.DeleteFlag:
        raise HTTPException(404, f"Location {location_id} not found")
    # 拠点の時差列を持たず、アプリ共通の日本時間で稼働枠を展開する。
    tz = get_settings().app_timezone
    s, e = to_jst_naive(start), to_jst_naive(end)
    if e <= s:
        raise HTTPException(422, "'to' must be after 'from'")
    return [WorkingInterval(start=a, end=b) for a, b in working_time(db, location_id, s, e, tz)]


routers.append(calendar_extra)

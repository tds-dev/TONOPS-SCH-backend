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
from app.services.calculation_settings_service import save_calculation_setting
from app.schemas.base import ApiModel, JstDatetime
from app.services.calendar_service import (
    delete_calendar,
    save_calendar,
    validate_calendar_exception_write,
    working_time,
)
from app.services.resource_order_service import (
    delete_resource,
    delete_resource_group,
    save_resource,
    save_resource_group,
)
from app.services.product_process_service import delete_product_process, save_product_process
from app.services.process_group_service import delete_process_group, save_process_group
from app.services.worker_service import delete_worker, save_worker
from app.services.worker_settings_service import (
    delete_worker_calendar,
    filter_worker_skill_maps,
    prevent_worker_skill_map_deletion,
    save_worker_calendar,
    save_worker_skill_map,
    validate_worker_exception,
    worker_working_time,
)
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
    crud_router(m.ResourceGroup, "/resource-groups", "Resources", order_by="SortOrder",
                write_handler=save_resource_group, delete_handler=delete_resource_group),
    crud_router(m.Resource, "/resources", "Resources", order_by="SortOrder",
                write_handler=save_resource, delete_handler=delete_resource),
    # 作業者は監査列を持たないため、既存の5列に合わせた専用保存・論理削除を使う。
    crud_router(m.Worker, "/workers", "Workers", order_by="WorkerID",
                write_handler=save_worker, delete_handler=delete_worker),
    # 通常稼働時間と担当工程は、作業者ごとの設定として保存する。
    crud_router(m.WorkerCalendar, "/worker-calendars", "Workers", order_by="DayOfWeek",
                write_handler=save_worker_calendar, delete_handler=delete_worker_calendar),
    crud_router(m.WorkerCalendarException, "/worker-calendar-exceptions", "Workers", order_by="StartAt",
                validate_write=validate_worker_exception),
    crud_router(m.WorkerSkillMap, "/worker-skill-maps", "Workers", order_by="ProductProcessID",
                write_handler=save_worker_skill_map, delete_handler=prevent_worker_skill_map_deletion,
                filter_list=filter_worker_skill_maps),
    crud_router(m.ProductSwitchTime, "/product-switch-times", "Configuration", validate_write=validate_switch_time),
    crud_router(m.ProductSwitchRule, "/product-switch-rules", "Configuration", validate_write=validate_switch_rule),
    crud_router(m.CalculationSetting, "/calculation-settings", "Configuration",
                write_handler=save_calculation_setting),
    crud_router(m.ProcessGroup, "/process-groups", "Products & processes", order_by="SortOrder",
                write_handler=save_process_group, delete_handler=delete_process_group),
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


# 作業者単位の週間稼働表示を、拠点の稼働時間APIと同じ日時形式で返す。
worker_extra = APIRouter(prefix="/workers", tags=["Workers"])


# 作業者本人の通常稼働時間と例外休日を、日本時間の指定期間へ展開する。
@worker_extra.get("/{worker_id}/working-time", response_model=list[WorkingInterval])
def get_worker_working_time(
    worker_id: int,
    start: datetime = Query(..., alias="from"),
    end: datetime = Query(..., alias="to"),
    db: Session = Depends(get_db),
):
    # 削除済みや存在しない本人を、通常勤務がない作業者として表示しない。
    worker = db.get(m.Worker, worker_id)
    if worker is None or worker.DeleteFlag:
        raise HTTPException(404, f"Worker {worker_id} not found")
    # 拠点カレンダーと同じ日本時間・終了日時を含まない期間指定を使う。
    tz = get_settings().app_timezone
    s, e = to_jst_naive(start), to_jst_naive(end)
    if e <= s:
        raise HTTPException(422, "'to' must be after 'from'")
    return [WorkingInterval(start=a, end=b) for a, b in worker_working_time(db, worker_id, s, e, tz)]


routers.append(worker_extra)

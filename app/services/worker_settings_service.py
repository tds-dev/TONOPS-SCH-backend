"""作業者の通常稼働時間・例外休日・スキルマップの保存と、日別稼働時間の取得処理。"""
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import HTTPException, Request
from sqlalchemy import false, select
from sqlalchemy.orm import Session

from app.models.masters import Location, Product, ProductProcess, Worker, WorkerCalendar, WorkerCalendarException, WorkerSkillMap
from app.services.calendar_service import _validate_work_times
from app.services.product_validation import _value
from app.services.worker_service import _locked_worker
from app.services.worktime import ExceptionSpec, Interval, WorkSpec, expand_working_time


# 有効な所属拠点の作業者を取得し、本人の削除と設定保存が同時に進まないよう保護する。
def _worker(db: Session, worker_id: int | None) -> Worker:
    worker = db.get(Worker, worker_id) if worker_id is not None else None
    if worker is None or worker.DeleteFlag:
        raise HTTPException(422, "有効な作業者を指定してください。")
    worker = _locked_worker(db, worker)
    # 削除済み拠点の作業者へ新しい設定を保存しない。
    location = db.get(Location, worker.LocationID)
    if location is None or location.DeleteFlag:
        raise HTTPException(422, "有効な拠点の作業者を指定してください。")
    return worker


# 任意の文字入力の上限を確認し、空欄を未設定に揃える。
def _optional_text(original: Any, values: dict[str, Any], key: str, label: str, maximum: int) -> None:
    value = _value(original, values, key)
    if value is not None and len(value) > maximum:
        raise HTTPException(422, f"{label}は{maximum}文字以内で入力してください。")
    if key in values and value is not None:
        values[key] = value.strip() or None


# 作業者の曜日・同日内の時間帯を確認し、既存カレンダーと同じ単位で勤務を保存する。
def save_worker_calendar(db: Session, original: WorkerCalendar | None, values: dict[str, Any], user: str) -> WorkerCalendar:
    worker_id = _value(original, values, "WorkerID")
    _worker(db, worker_id)
    if original is not None:
        db.refresh(original)
        if original.DeleteFlag:
            raise HTTPException(404, "削除済みの通常稼働時間です。")
        if original.WorkerID != worker_id:
            raise HTTPException(422, "登録済みの通常稼働時間の作業者は変更できません。")
    if "DeleteFlag" in values and values["DeleteFlag"] is not False:
        raise HTTPException(422, "通常稼働時間を削除するときは削除操作を使ってください。")
    # 曜日番号は拠点カレンダーと同じ日曜0～土曜6とする。
    day = _value(original, values, "DayOfWeek")
    if not isinstance(day, int) or isinstance(day, bool) or not 0 <= day <= 6:
        raise HTTPException(422, "曜日は0（日曜）～6（土曜）で指定してください。")
    _validate_work_times(_value(original, values, "StartTime"), _value(original, values, "EndTime"),
                         original.WorkerCalendarsID if original is not None else None)
    _optional_text(original, values, "WorkName", "勤務名", 50)
    if original is None:
        row = WorkerCalendar(**values, CreatedBy=user)
        db.add(row)
        return row
    for key, value in values.items():
        setattr(original, key, value)
    original.UpdatedBy = user
    return original


# 通常稼働時間だけを論理削除し、本人へ直接紐づく例外休日には触れない。
def delete_worker_calendar(db: Session, original: WorkerCalendar, user: str) -> None:
    _worker(db, original.WorkerID)
    db.refresh(original)
    if original.DeleteFlag:
        raise HTTPException(404, "削除済みの通常稼働時間です。")
    original.DeleteFlag = True
    original.UpdatedBy = user


# 例外休日の作業者を直接確認し、勤務未登録でも休日の登録を受け付ける。
def validate_worker_exception(db: Session, original: WorkerCalendarException | None, values: dict[str, Any]) -> None:
    worker_id = _value(original, values, "WorkerID")
    _worker(db, worker_id)
    if original is not None and original.WorkerID != worker_id:
        raise HTTPException(422, "登録済み例外休日の作業者は変更できません。")
    # 時刻だけでなく日付を持つため、複数日にまたがる休日も同じ条件で受け付ける。
    start, end = _value(original, values, "StartAt"), _value(original, values, "EndAt")
    if not isinstance(start, datetime) or not isinstance(end, datetime) or end <= start:
        raise HTTPException(422, "終了日時は開始日時より後にしてください。")
    _optional_text(original, values, "Remark", "備考", 500)


# 作業者の通常稼働時間を展開し、本人に直接紐づく例外休日を差し引く。
def worker_working_time(db: Session, worker_id: int, start: datetime, end: datetime, tz: str) -> list[Interval]:
    rows = list(db.scalars(select(WorkerCalendar).where(
        WorkerCalendar.WorkerID == worker_id, WorkerCalendar.DeleteFlag == false(),
    ).order_by(WorkerCalendar.DayOfWeek, WorkerCalendar.StartTime, WorkerCalendar.WorkerCalendarsID)))
    for row in rows:
        _validate_work_times(row.StartTime, row.EndTime, row.WorkerCalendarsID)
    # 勤務行の番号を経由せず、本人の全例外休日を直接取得する。
    exceptions = list(db.scalars(select(WorkerCalendarException).where(
        WorkerCalendarException.WorkerID == worker_id,
    )))
    # 通常勤務が未登録の作業者は、週表示上の稼働なしとする。
    return expand_working_time([WorkSpec(row.DayOfWeek, row.StartTime, row.EndTime) for row in rows],
                               [ExceptionSpec(row.StartAt, row.EndAt) for row in exceptions], start, end, tz)


# 同じ拠点の製品工程だけへ担当可否・日上限・備考を保存し、監査列のない既存定義を維持する。
def save_worker_skill_map(db: Session, original: WorkerSkillMap | None, values: dict[str, Any], _user: str) -> WorkerSkillMap:
    worker_id = _value(original, values, "WorkerID")
    worker = _worker(db, worker_id)
    # 登録済みの組合せを別人・別工程へ移さず、既存の担当関係を保つ。
    process_id = _value(original, values, "ProductProcessID")
    if original is not None:
        db.refresh(original)
        if original.WorkerID != worker_id or original.ProductProcessID != process_id:
            raise HTTPException(422, "登録済みスキルマップの作業者・工程は変更できません。")
    process = db.get(ProductProcess, process_id) if process_id is not None else None
    product = db.get(Product, process.ProductID) if process is not None else None
    if product is None or product.DeleteFlag or product.LocationID != worker.LocationID:
        raise HTTPException(422, "同じ拠点の有効な製品工程を指定してください。")
    # 同じ担当関係の二重登録を、DB制約違反になる前に案内する。
    duplicate = db.scalar(select(WorkerSkillMap.WorkerSkillMapID).where(
        WorkerSkillMap.WorkerID == worker_id, WorkerSkillMap.ProductProcessID == process_id,
    ))
    if duplicate is not None and (original is None or duplicate != original.WorkerSkillMapID):
        raise HTTPException(409, "この工程のスキルマップは登録済みです。一覧から編集してください。")
    can_execute = _value(original, values, "CanExecute", False)
    if not isinstance(can_execute, bool):
        raise HTTPException(422, "担当可否を指定してください。")
    # 日上限は正の数量・小数第3位まで。未設定は上限なしとして保持する。
    maximum = _value(original, values, "MaxDailyQuantity")
    if maximum is not None:
        try:
            quantity = Decimal(str(maximum))
            valid = quantity.is_finite() and 0 < quantity <= Decimal('999999999999999.999')
            valid = valid and quantity.quantize(Decimal('0.001')) == quantity
        except (InvalidOperation, ValueError):
            valid = False
        if not valid:
            raise HTTPException(422, "1日の生産上限は正の数量を小数第3位までで入力してください。")
    _optional_text(original, values, "Remarks", "備考", 500)
    if original is None:
        row = WorkerSkillMap(**values)
        db.add(row)
        return row
    for key, value in values.items():
        setattr(original, key, value)
    return original


# 全工程との対応関係は残し、担当可否の変更から担当を解除する。
def prevent_worker_skill_map_deletion(db: Session, original: WorkerSkillMap, _user: str) -> None:
    _worker(db, original.WorkerID)
    raise HTTPException(409, "スキルマップは削除せず、担当可能を無効にしてください。")


# 一覧では有効な同じ拠点の製品工程だけを表示し、削除済み製品との既存リンクは保持する。
def filter_worker_skill_maps(statement: Any, _request: Request) -> Any:
    return statement.join(ProductProcess, ProductProcess.ProductProcessID == WorkerSkillMap.ProductProcessID).join(
        Product, Product.ProductID == ProductProcess.ProductID,
    ).join(Worker, Worker.WorkerID == WorkerSkillMap.WorkerID).where(
        Product.DeleteFlag == false(), Worker.DeleteFlag == false(), Product.LocationID == Worker.LocationID,
    )

"""LocationIDに紐づく週次勤務・停止予定の取得、入力確認、勤務削除時の保護。"""
from datetime import datetime, time
from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from sqlalchemy import false, select
from sqlalchemy.orm import Session

from app.models.masters import Calendar, CalendarException, Location, Resource
from app.services.worktime import ExceptionSpec, Interval, WorkSpec, expand_working_time


# 部分更新で送信されなかった値を、更新前のレコードから補う。
def _value(original: Any, values: dict[str, Any], key: str) -> Any:
    return values[key] if key in values else getattr(original, key, None)


# 有効な拠点を取得し、SQL Serverでは同じ拠点への同時書込みを順番に処理する。
def _location(db: Session, location_id: int | None) -> Location:
    # 最後の勤務行の削除と停止予定の保存が競合しないよう、同じ拠点の変更を直列にする。
    statement = select(Location).where(Location.LocationID == location_id).with_hint(
        Location, "WITH (UPDLOCK, HOLDLOCK)", dialect_name="mssql",
    ).execution_options(populate_existing=True)
    location = db.scalar(statement) if location_id is not None else None
    if location is None or location.DeleteFlag:
        raise HTTPException(422, "有効な拠点を指定してください。")
    return location


# 設備の所属拠点と同時作業数・稼働上限（時間・数量）を確認する。勤務は所属拠点から共通で参照する。
def validate_resource_location_write(db: Session, original: Resource | None, values: dict[str, Any]) -> None:
    location_id = _value(original, values, "LocationID")
    _location(db, location_id)
    # 同時作業数はNULLを許可し、指定時のみNUMERIC(9,2)の正の範囲を確認する。
    if "Capacity" in values and values["Capacity"] is not None:
        capacity = Decimal(str(values["Capacity"]))
        if (not capacity.is_finite() or capacity < 1 or capacity > Decimal("9999999.99")
                or capacity != capacity.quantize(Decimal("0.01"))):
            raise HTTPException(422, "同時作業数は1～9999999.99、小数点以下2桁以内で入力してください。")
    # 未送信なら既存値を保持し、NULLの送信は上限設定の解除として受け付ける。
    if "DailyCapacityHours" in values and values["DailyCapacityHours"] is not None:
        hours = Decimal(str(values["DailyCapacityHours"]))
        # SQL Serverでの丸めや桁あふれを防ぎ、NUMERIC(5,2)へそのまま保存できる値に限定する。
        if (not hours.is_finite() or hours < 0 or hours > Decimal("999.99")
                or hours != hours.quantize(Decimal("0.01"))):
            raise HTTPException(422, "一日における稼働上限時間は0～999.99時間、小数点以下2桁以内で入力してください。")
    # 1日の稼働上限数量はNULLを許可し、指定時のみ1以上の整数を確認する。
    if "DailyCapacityQuantity" in values and values["DailyCapacityQuantity"] is not None:
        quantity = values["DailyCapacityQuantity"]
        if isinstance(quantity, bool) or not isinstance(quantity, int) or not 1 <= quantity <= 2147483647:
            raise HTTPException(422, "1日の稼働上限数量は1～2147483647の整数で入力してください。")


# 保存・計算読込で同じ時刻確認を使い、同日内の勤務だけを受け付ける。
def _validate_work_times(start_time: Any, end_time: Any, calendar_id: int | None = None) -> None:
    # 既存の不正な勤務を、利用者が特定して修正するための表示。
    target = f"勤務行 {calendar_id}の" if calendar_id is not None else "勤務の"
    for value in (start_time, end_time):
        if not isinstance(value, time) or value.tzinfo is not None:
            raise HTTPException(422, f"{target}時刻は日本時間の時刻で指定してください。")
    if end_time <= start_time:
        raise HTTPException(422, f"{target}終了時刻は開始時刻より後にしてください（日をまたぐ勤務は登録できません）。")


# 所属拠点・曜日・同日内の時間帯を確認して週次勤務を保存する。
def save_calendar(db: Session, original: Calendar | None, values: dict[str, Any], user: str) -> Calendar:
    location_id = _value(original, values, "LocationID")
    _location(db, location_id)
    if original is not None:
        db.refresh(original)
        if original.DeleteFlag:
            raise HTTPException(404, "削除済みの勤務行です。")
    if original is not None and original.LocationID != location_id:
        raise HTTPException(422, "登録済み勤務行の拠点は変更できません。")
    if values.get("DeleteFlag"):
        raise HTTPException(422, "勤務行を削除するときは削除操作を使ってください。")
    # 曜日と勤務時刻を確認し、終了が開始より後の同日勤務に限定する。
    day = _value(original, values, "DayOfWeek")
    if not isinstance(day, int) or isinstance(day, bool) or not 0 <= day <= 6:
        raise HTTPException(422, "曜日は0（日曜）～6（土曜）で指定してください。")
    _validate_work_times(
        _value(original, values, "StartTime"), _value(original, values, "EndTime"),
        original.CalendarID if original is not None else None,
    )
    work_name = _value(original, values, "WorkName")
    if work_name is not None and len(work_name) > 50:
        raise HTTPException(422, "勤務名は50文字以内で入力してください。")
    if original is None:
        row = Calendar(**values, CreatedBy=user)
        db.add(row)
    else:
        row = original
        for key, value in values.items():
            setattr(row, key, value)
        row.UpdatedBy = user
    db.flush()
    return row


# 勤務行を論理削除し、停止予定がある拠点の最後の勤務行は保護する。
def delete_calendar(db: Session, row: Calendar, user: str) -> None:
    _location(db, row.LocationID)
    db.refresh(row)
    if row.DeleteFlag:
        raise HTTPException(404, "削除済みの勤務行です。")
    # 最後の勤務行かを、同じ拠点の残る有効勤務の有無で判断する。
    remaining_id = db.scalar(select(Calendar.CalendarID).where(
        Calendar.LocationID == row.LocationID, Calendar.CalendarID != row.CalendarID,
        Calendar.DeleteFlag == false(),
    ).order_by(Calendar.CalendarID))
    if remaining_id is None:
        # 停止予定は勤務行を経由せず、所属拠点から直接検索する。
        exception_id = db.scalar(select(CalendarException.ExceptionID).where(
            CalendarException.LocationID == row.LocationID,
        ))
        if exception_id is not None:
            raise HTTPException(409, "休日・停止の例外が残っています。最後の勤務行を削除する前に例外を削除してください。")
    row.DeleteFlag = True
    row.UpdatedBy = user


# 停止予定の所属拠点と、開始・終了日時の順序を確認する。
def validate_calendar_exception_write(db: Session, original: CalendarException | None, values: dict[str, Any]) -> None:
    location_id = _value(original, values, "LocationID")
    _location(db, location_id)
    if original is not None and original.LocationID != location_id:
        raise HTTPException(422, "登録済み停止例外の拠点は変更できません。")
    # 勤務未登録時に停止予定だけを作らない従来の受付条件を維持する。
    existing_id = db.scalar(select(Calendar.CalendarID).where(
        Calendar.LocationID == location_id, Calendar.DeleteFlag == false(),
    ).limit(1))
    if existing_id is None:
        raise HTTPException(422, "週間の稼働時間を登録してから停止予定を設定してください。")
    start = _value(original, values, "StartAt")
    end = _value(original, values, "EndAt")
    if not isinstance(start, datetime) or not isinstance(end, datetime) or end <= start:
        raise HTTPException(422, "終了日時は開始日時より後にしてください。")


# 指定拠点の全有効勤務と、その拠点に直接紐づく停止予定を取得する。
def calendar_specs(db: Session, location_id: int) -> tuple[list[WorkSpec], list[ExceptionSpec]]:
    rows = db.scalars(select(Calendar).where(
        Calendar.LocationID == location_id, Calendar.DeleteFlag == false(),
    ).order_by(Calendar.DayOfWeek, Calendar.StartTime, Calendar.CalendarID)).all()
    # 廃止前の夜勤などが残る場合は、対象勤務行を示して計算前に修正を案内する。
    for row in rows:
        _validate_work_times(row.StartTime, row.EndTime, row.CalendarID)
    # 停止予定は同じ拠点の全勤務へ適用する。
    exceptions = db.scalars(select(CalendarException).where(
        CalendarException.LocationID == location_id,
    )).all()
    return (
        [WorkSpec(row.DayOfWeek, row.StartTime, row.EndTime) for row in rows],
        [ExceptionSpec(row.StartAt, row.EndAt) for row in exceptions],
    )


# 拠点の週次勤務と停止例外を、指定期間の日本時間の稼働区間へ展開する。
def working_time(db: Session, location_id: int, start: datetime, end: datetime, tz: str) -> list[Interval]:
    work_rows, exceptions = calendar_specs(db, location_id)
    # 勤務の登録がない拠点だけ常時稼働とする。登録済み勤務の休日は稼働なしのまま扱う。
    if not work_rows:
        return [(start, end)] if end > start else []
    return expand_working_time(work_rows, exceptions, start, end, tz)

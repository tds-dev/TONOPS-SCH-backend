"""拠点共通の週次勤務・停止例外の取得、入力確認、代表勤務行の参照管理。"""
from datetime import datetime, time
from typing import Any

from fastapi import HTTPException, Request
from sqlalchemy import false, select
from sqlalchemy.orm import Session

from app.models.masters import Calendar, CalendarException, Location, Resource
from app.services.worktime import ExceptionSpec, Interval, WorkSpec, expand_working_time


# 部分更新で送信されなかった値を、更新前のレコードから補う。
def _value(original: Any, values: dict[str, Any], key: str) -> Any:
    return values[key] if key in values else getattr(original, key, None)


# 有効な拠点を取得し、SQL Serverでは同じ拠点への同時書込みを順番に処理する。
def _location(db: Session, location_id: int | None) -> Location:
    # 代表行の選択と付け替えを確定まで保護し、待機後は最新の保存値を読み直す。
    statement = select(Location).where(Location.LocationID == location_id).with_hint(
        Location, "WITH (UPDLOCK, HOLDLOCK)", dialect_name="mssql",
    ).execution_options(populate_existing=True)
    location = db.scalar(statement) if location_id is not None else None
    if location is None or location.DeleteFlag:
        raise HTTPException(422, "有効な拠点を指定してください。")
    return location


# カレンダーの参照先が同じ拠点の有効な勤務行かを確認する。
def _calendar(db: Session, calendar_id: int, location_id: int) -> Calendar:
    calendar = db.get(Calendar, calendar_id)
    if calendar is not None:
        db.refresh(calendar)
    if calendar is None or calendar.DeleteFlag or calendar.LocationID != location_id:
        raise HTTPException(422, "同じ拠点の有効な勤務行を指定してください。")
    return calendar


# 拠点の代表勤務行が別の拠点を指さないようにする。
def validate_location_write(db: Session, original: Location | None, values: dict[str, Any]) -> None:
    if original is not None:
        _location(db, original.LocationID)
    calendar_id = _value(original, values, "CalendarID")
    if calendar_id is not None:
        if original is None:
            raise HTTPException(422, "拠点を作成してから勤務行を登録してください。")
        _calendar(db, calendar_id, original.LocationID)
    elif original is not None and "CalendarID" in values:
        # 勤務が残る拠点の代表を外し、計算が常時稼働へ戻ることを防ぐ。
        existing = db.scalar(select(Calendar.CalendarID).where(
            Calendar.LocationID == original.LocationID, Calendar.DeleteFlag == false(),
        ))
        if existing is not None:
            raise HTTPException(422, "勤務行がある拠点のCalendarIDは解除できません。")


# 設備に指定する勤務行を、設備と同じ拠点に限定する。
def validate_resource_calendar_write(db: Session, original: Resource | None, values: dict[str, Any]) -> None:
    location_id = _value(original, values, "LocationID")
    _location(db, location_id)
    calendar_id = _value(original, values, "CalendarID")
    if calendar_id is not None:
        _calendar(db, calendar_id, location_id)


# 保存・計算読込で同じ時刻確認を使い、同日内の勤務だけを受け付ける。
def _validate_work_times(start_time: Any, end_time: Any, calendar_id: int | None = None) -> None:
    # 既存の不正な勤務を、利用者が特定して修正するための表示。
    target = f"勤務行 {calendar_id}の" if calendar_id is not None else "勤務の"
    for value in (start_time, end_time):
        if not isinstance(value, time) or value.tzinfo is not None:
            raise HTTPException(422, f"{target}時刻は日本時間の時刻で指定してください。")
    if end_time <= start_time:
        raise HTTPException(422, f"{target}終了時刻は開始時刻より後にしてください（日をまたぐ勤務は登録できません）。")


# 週次勤務を保存し、初回は拠点の代表勤務行も設定する。
def save_calendar(db: Session, original: Calendar | None, values: dict[str, Any], user: str) -> Calendar:
    location_id = _value(original, values, "LocationID")
    location = _location(db, location_id)
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
    if location.CalendarID is None:
        location.CalendarID = row.CalendarID
        location.UpdatedBy = user
    return row


# 勤務行を削除し、残る行へ拠点・設備・停止例外の参照を付け替える。
def delete_calendar(db: Session, row: Calendar, user: str) -> None:
    location = _location(db, row.LocationID)
    db.refresh(row)
    if row.DeleteFlag:
        raise HTTPException(404, "削除済みの勤務行です。")
    # 同じ拠点の残る勤務行。最後の1行なら参照は解除する。
    replacement_id = db.scalar(select(Calendar.CalendarID).where(
        Calendar.LocationID == row.LocationID, Calendar.CalendarID != row.CalendarID,
        Calendar.DeleteFlag == false(),
    ).order_by(Calendar.CalendarID))
    if replacement_id is None:
        exception_id = db.scalar(select(CalendarException.ExceptionID).join(
            Calendar, Calendar.CalendarID == CalendarException.CalendarID,
        ).where(Calendar.LocationID == row.LocationID))
        if exception_id is not None:
            raise HTTPException(409, "休日・停止の例外が残っています。最後の勤務行を削除する前に例外を削除してください。")
    if location.CalendarID == row.CalendarID:
        location.CalendarID = replacement_id
        location.UpdatedBy = user
    # 削除済み設備も含めて参照を更新し、旧勤務行を参照したままにしない。
    for resource in db.scalars(select(Resource).where(Resource.CalendarID == row.CalendarID)):
        resource.CalendarID = replacement_id
        resource.UpdatedBy = user
    for exception in db.scalars(select(CalendarException).where(CalendarException.CalendarID == row.CalendarID)):
        exception.CalendarID = replacement_id
        exception.UpdatedBy = user
    row.DeleteFlag = True
    row.UpdatedBy = user


# 停止例外の有効な参照先と、開始・終了日時の順序を確認する。
def validate_calendar_exception_write(db: Session, original: CalendarException | None, values: dict[str, Any]) -> None:
    calendar_id = _value(original, values, "CalendarID")
    calendar = db.get(Calendar, calendar_id) if calendar_id is not None else None
    if calendar is None or calendar.DeleteFlag:
        raise HTTPException(422, "有効な勤務行を指定してください。")
    _location(db, calendar.LocationID)
    # 代表行の削除処理を待った場合に、削除後の行へ例外を作らないよう再確認する。
    _calendar(db, calendar_id, calendar.LocationID)
    if original is not None:
        previous = db.get(Calendar, original.CalendarID)
        if previous.LocationID != calendar.LocationID:
            raise HTTPException(422, "登録済み停止例外の拠点は変更できません。")
    start = _value(original, values, "StartTime")
    end = _value(original, values, "EndTime")
    if not isinstance(start, datetime) or not isinstance(end, datetime) or end <= start:
        raise HTTPException(422, "終了日時は開始日時より後にしてください。")


# 一覧では勤務行IDに加え、拠点内の全勤務行に紐づく例外を検索できるようにする。
def filter_calendar_exceptions(statement: Any, request: Request) -> Any:
    location_id = request.query_params.get("locationId")
    if location_id is not None:
        try:
            location_id = int(location_id)
        except ValueError:
            raise HTTPException(422, "拠点番号は整数で指定してください。") from None
        statement = statement.where(CalendarException.CalendarID.in_(
            select(Calendar.CalendarID).where(Calendar.LocationID == location_id),
        ))
    return statement


# 指定勤務行と同じ拠点の全有効勤務と、その拠点の停止例外を取得する。
def calendar_specs(db: Session, calendar_id: int) -> tuple[list[WorkSpec], list[ExceptionSpec]]:
    calendar = db.get(Calendar, calendar_id)
    if calendar is None or calendar.DeleteFlag:
        return [], []
    rows = db.scalars(select(Calendar).where(
        Calendar.LocationID == calendar.LocationID, Calendar.DeleteFlag == false(),
    ).order_by(Calendar.DayOfWeek, Calendar.StartTime, Calendar.CalendarID)).all()
    # 廃止前の夜勤などが残る場合は、対象勤務行を示して計算前に修正を案内する。
    for row in rows:
        _validate_work_times(row.StartTime, row.EndTime, row.CalendarID)
    # 例外は登録先の勤務行に関係なく、同じ拠点の全勤務へ適用する。
    exceptions = db.scalars(select(CalendarException).join(
        Calendar, Calendar.CalendarID == CalendarException.CalendarID,
    ).where(Calendar.LocationID == calendar.LocationID)).all()
    return (
        [WorkSpec(row.DayOfWeek, row.StartTime, row.EndTime) for row in rows],
        [ExceptionSpec(row.StartTime, row.EndTime) for row in exceptions],
    )


# 拠点の週次勤務と停止例外を、指定期間の日本時間の稼働区間へ展開する。
def working_time(db: Session, calendar_id: int, start: datetime, end: datetime, tz: str) -> list[Interval]:
    work_rows, exceptions = calendar_specs(db, calendar_id)
    return expand_working_time(work_rows, exceptions, start, end, tz)

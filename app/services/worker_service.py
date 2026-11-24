"""作業者の基本情報を保存・論理削除し、同じ拠点の製品工程との担当関係を作成する処理。"""
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.masters import Location, Worker
from app.services.product_validation import _name, _value
from app.services.worker_process_service import add_process_skill_maps


# 1日の作業台数・生産上限がNULLまたは正の数量（小数第3位まで）であることを確認する。
def validate_max_daily_quantity(value: Any, label: str) -> None:
    if value is None:
        return
    try:
        quantity = Decimal(str(value))
        valid = quantity.is_finite() and 0 < quantity <= Decimal("999999999999999.999")
        valid = valid and quantity.quantize(Decimal("0.001")) == quantity
    except (InvalidOperation, ValueError):
        valid = False
    if not valid:
        raise HTTPException(422, f"{label}は正の数量を小数第3位までで入力してください。")


# 編集・削除の対象を最新の状態で取得し、削除済み作業者への再保存を防ぐ。
def _locked_worker(db: Session, original: Worker) -> Worker:
    # SQL Serverでは同じ作業者への変更を順番に処理する。
    worker = db.scalar(select(Worker).where(Worker.WorkerID == original.WorkerID).with_hint(
        Worker, "WITH (UPDLOCK, HOLDLOCK)", dialect_name="mssql",
    ).execution_options(populate_existing=True))
    if worker is None or worker.DeleteFlag:
        raise HTTPException(404, "削除済みの作業者です。一覧を再読込してください。")
    return worker


# 作業者名・備考を検証して保存する。共通APIから受け取る操作者は、この5列のモデルには保存しない。
def save_worker(db: Session, original: Worker | None, values: dict[str, Any], _user: str) -> Worker:
    if original is not None:
        original = _locked_worker(db, original)
    _name(original, values, "WorkerName", "作業者名")
    # 登録後の拠点移動で、既存の担当工程・勤務の所属が食い違わないよう保護する。
    location_id = _value(original, values, "LocationID")
    if original is not None and original.LocationID != location_id:
        raise HTTPException(422, "登録済み作業者の拠点は変更できません。")
    # 実在する有効な拠点への登録だけを受け付ける。
    location = db.get(Location, location_id) if location_id is not None else None
    if location is None or location.DeleteFlag:
        raise HTTPException(422, "有効な拠点を指定してください。")
    if "DeleteFlag" in values and values["DeleteFlag"] is not False:
        raise HTTPException(422, "作業者を削除するときは削除操作を使ってください。")
    # 1日の作業台数上限はNULL（上限なし）または正の数量（小数第3位まで）とする。
    validate_max_daily_quantity(_value(original, values, "MaxDailyQuantity"), "1日の作業台数上限")
    # 任意入力の備考は500文字までとし、空欄は未設定として保存する。
    remarks = _value(original, values, "Remarks")
    if remarks is not None and len(remarks) > 500:
        raise HTTPException(422, "備考は500文字以内で入力してください。")
    if "Remarks" in values and remarks is not None:
        values["Remarks"] = remarks.strip() or None
    if original is None:
        # 既存テーブルにない監査列は追加せず、本人情報と担当関係を同時に保存する。
        worker = Worker(**values)
        db.add(worker)
        add_process_skill_maps(db, worker)
        return worker
    for key, value in values.items():
        setattr(original, key, value)
    return original


# 担当工程・勤務・不在の既存情報は残し、作業者だけを通常一覧の対象外にする。
def delete_worker(db: Session, original: Worker, _user: str) -> None:
    worker = _locked_worker(db, original)
    worker.DeleteFlag = True

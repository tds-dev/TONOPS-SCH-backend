"""オーダー保存時の入力・所属拠点・製品と、既存タスクへの影響を確認する処理。"""
from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.masters import Location, Product
from app.models.transactions import (
    ORDER_STATUSES, WorkActual, Order, PlanAssignment, Task,
)


# 新規登録時にDBが補う値。明示的なnullと未送信を区別する。
ORDER_DEFAULTS = {"Status": "OPEN", "Priority": 50}


# 送信された値と既存値を組み合わせ、保存してよい入力か確認する。
def validate_order_write(db: Session, original: Order | None, values: dict[str, Any]) -> None:
    # 部分更新で送信されていない項目は、元の保存値を使用する。
    def value(key: str):
        return values[key] if key in values else getattr(original, key) if original else ORDER_DEFAULTS.get(key)

    # 数量は浮動小数とDBの十進数の表現差を除き、実際に変わったか判定する。
    def changed(key: str) -> bool:
        if original is None or key not in values:
            return False
        # 変更前後の保存値。未指定の数量はnullのまま比較する。
        before, after = getattr(original, key), values[key]
        if key == "Quantity" and before is not None and after is not None:
            return Decimal(str(before)) != Decimal(str(after))
        return before != after

    # 文字項目は前後の空白を除き、DBの最大文字数を超える入力を防ぐ。
    for key, label, maximum, required in (
        ("WBSNumber", "WBS番号", 30, True), ("OrderName", "名称", 200, True),
        ("CustomerName", "納品先", 100, False), ("Remarks", "備考", 500, False),
    ):
        # 今回保存する文字列。
        text = value(key)
        if key in values and isinstance(text, str):
            text = text.strip()
            values[key] = text if required else text or None
        if required and (text is None or not text.strip()):
            raise HTTPException(422, f"{label}を入力してください。")
        if text is not None and len(text) > maximum:
            raise HTTPException(422, f"{label}は{maximum}文字以内にしてください。")

    # 状態の保存値が、オーダーで使用できる選択肢に含まれるか確認する。
    if value("Status") not in ORDER_STATUSES:
        raise HTTPException(422, "状態を選び直してください。")

    # 数量はDBのNUMERIC(18,3)に収まる、0以上の数値に制限する。
    quantity = value("Quantity")
    if quantity is not None:
        # 小数の桁を丸めずに確認するため、十進数として比較する。
        numeric = Decimal(str(quantity))
        if not numeric.is_finite() or numeric < 0 or numeric >= Decimal("1e15") or numeric != numeric.quantize(Decimal("0.001")):
            raise HTTPException(422, "数量は0以上・15桁以内・小数点以下3桁以内で入力してください。")
    # 優先度は1を最優先とする整数。
    priority = value("Priority")
    if priority is None or not 1 <= priority <= 2147483647:
        raise HTTPException(422, "優先度は1～2147483647の整数で入力してください。")
    # 更新操作で所属拠点を変え、タスクと設備の所属が食い違うことを防ぐ。
    location_id = value("LocationID")
    if original is not None and location_id != original.LocationID:
        raise HTTPException(422, "登録済みオーダーの拠点は変更できません。")
    # 論理削除済みの拠点には新しいオーダーを保存しない。
    location = db.get(Location, location_id) if location_id is not None else None
    if location is None or location.DeleteFlag:
        raise HTTPException(422, "有効な拠点を指定してください。")
    # 日単位では保存済み時刻に左右されず日付を比較し、既存の日時自体は変更しない。
    release, deadline = value("ReleaseAt"), value("DeadLine")
    if release is not None and deadline is not None:
        day_mode = location.LocationTimeUnit == "DAY"
        invalid_period = release.date() > deadline.date() if day_mode else release > deadline
        if invalid_period:
            message = "納期は製造開始可能日以降に設定してください。" if day_mode else "納期は製造開始可能日時以降に設定してください。"
            raise HTTPException(422, message)
    # 製品はオーダーと同じ拠点のものだけ許可する。
    # 既存参照を変えない編集では、削除済みマスタの参照値を保持できるようにする。
    references_changed = original is None or changed("ProductID")
    product_id = value("ProductID")
    product = db.get(Product, product_id) if product_id is not None else None
    if references_changed and product_id is not None and (product is None or product.DeleteFlag or product.LocationID != location_id):
        raise HTTPException(422, "同じ拠点の有効な製品を指定してください。")

    # WBS番号は小分けロット等で同一拠点内の複数オーダーに共通指定できるため、重複チェックは行わない。

    # 計画・実績があるタスクの内容とオーダーが食い違わないよう、生成元の変更を防ぐ。
    if original is not None and any(changed(key) for key in ("ProductID", "Quantity")):
        # このオーダーに属するタスクの識別番号。
        task_ids = select(Task.TaskID).where(Task.OrderID == original.OrderID)
        if (db.scalar(select(PlanAssignment.AssignmentID).where(PlanAssignment.TaskID.in_(task_ids)).limit(1)) is not None
                or db.scalar(select(WorkActual.WorkActualID).where(WorkActual.TaskID.in_(task_ids)).limit(1)) is not None
                or db.scalar(select(Task.TaskID).where(Task.OrderID == original.OrderID, Task.Status != "NOT_STARTED").limit(1)) is not None):
            raise HTTPException(409, "計画に割付済み、または作業開始・実績登録済みのため、製品・数量は変更できません。")

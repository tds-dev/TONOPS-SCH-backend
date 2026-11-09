"""製品・製品工程・実行候補の入力と、所属拠点の整合性を確認する処理。"""
from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.masters import Location, Product, ProductProcess, Resource, ResourceGroup


# 部分更新では未送信の項目を元の保存値で補う。
def _value(original: Any, values: dict[str, Any], key: str, default: Any = None) -> Any:
    if key in values:
        return values[key]
    if original is not None:
        return getattr(original, key)
    return default


# 名称の前後の空白を除き、必須と最大文字数を確認する。
def _name(original: Any, values: dict[str, Any], key: str, label: str) -> str:
    # 今回保存する名称。Noneを空文字へ変換して必須チェックを共通化する。
    name = str(_value(original, values, key) or "").strip()
    if not name or len(name) > 100:
        raise HTTPException(422, f"{label}は1～100文字で入力してください。")
    if key in values:
        values[key] = name
    return name


# 工程番号や分数に使用する整数の範囲を確認する。
def _integer(value: Any, label: str, minimum: int = 0) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= 2147483647:
        raise HTTPException(422, f"{label}は{minimum}～2147483647の整数で入力してください。")


# 製品の名称、所属拠点、拠点内の名称重複を確認する。
def validate_product_write(db: Session, original: Product | None, values: dict[str, Any]) -> None:
    # 保存する名称と拠点。登録済み製品の所属を変えて既存オーダーと食い違うことを防ぐ。
    name = _name(original, values, "ProductName", "製品名")
    location_id = _value(original, values, "LocationID")
    if original is not None and location_id != original.LocationID:
        raise HTTPException(422, "登録済み製品の拠点は変更できません。")
    # 新しい製品を登録できる有効な拠点。
    location = db.get(Location, location_id) if location_id is not None else None
    if location is None or location.DeleteFlag:
        raise HTTPException(422, "有効な拠点を指定してください。")
    # 削除済みも含め、同じ拠点で製品名を重複させない。
    duplicate = db.scalar(select(Product.ProductID).where(Product.LocationID == location_id, Product.ProductName == name))
    if duplicate is not None and (original is None or duplicate != original.ProductID):
        raise HTTPException(409, "同じ拠点で製品名が登録済みです。別の名称を入力してください。")


# 製品工程の名称、順序、待ち時間と製品参照を確認する。
def validate_product_process_write(db: Session, original: ProductProcess | None, values: dict[str, Any]) -> None:
    _name(original, values, "ProcessName", "工程名")
    # 製品の所属先は登録後に変更せず、既存タスクの生成元を保持する。
    product_id = _value(original, values, "ProductID")
    if original is not None and product_id != original.ProductID:
        raise HTTPException(422, "登録済み工程の製品は変更できません。")
    # 工程を登録する有効な製品。
    product = db.get(Product, product_id) if product_id is not None else None
    if product is None or product.DeleteFlag:
        raise HTTPException(422, "有効な製品を指定してください。")
    # 工程番号と、この工程の後に必要な最小・最大待ち時間。
    sequence = _value(original, values, "SequenceNumber")
    minimum = _value(original, values, "MinLagAfterMin", 0)
    maximum = _value(original, values, "MaxLagAfterMin")
    _integer(sequence, "工程番号", 1)
    _integer(minimum, "最小待ち時間")
    if maximum is not None:
        _integer(maximum, "最大待ち時間")
        if maximum < minimum:
            raise HTTPException(422, "最大待ち時間は最小待ち時間以上にしてください。")
    # 別製品では同じ工程番号を使えるが、同じ製品内では重複させない。
    duplicate = db.scalar(select(ProductProcess.ProductProcessID).where(
        ProductProcess.ProductID == product_id, ProductProcess.SequenceNumber == sequence,
    ))
    if duplicate is not None and (original is None or duplicate != original.ProductProcessID):
        raise HTTPException(409, "同じ製品内で工程番号が重複しています。")


# 工程の実行候補を同じ拠点に限定し、設備かグループの片方と所要時間を確認する。
def validate_product_process_resource_write(db: Session, original: Any, values: dict[str, Any]) -> None:
    # この候補が属する工程と製品。
    process_id = _value(original, values, "ProductProcessID")
    if original is not None and process_id != original.ProductProcessID:
        raise HTTPException(422, "登録済み実行候補の工程は変更できません。")
    process = db.get(ProductProcess, process_id) if process_id is not None else None
    product = db.get(Product, process.ProductID) if process is not None else None
    if product is None or product.DeleteFlag:
        raise HTTPException(422, "有効な製品工程を指定してください。")
    # 設備とグループは排他的に指定し、製品と同じ拠点の有効な候補だけを許可する。
    resource_id = _value(original, values, "ResourceID")
    group_id = _value(original, values, "ResourceGroupID")
    if (resource_id is None) == (group_id is None):
        raise HTTPException(422, "リソースかグループのどちらか一方だけを指定してください。")
    target = db.get(Resource, resource_id) if resource_id is not None else db.get(ResourceGroup, group_id)
    if target is None or target.DeleteFlag or target.LocationID != product.LocationID:
        raise HTTPException(422, "製品と同じ拠点の有効なリソースかグループを指定してください。")
    # 準備・固定は整数分、数量当たり時間は小数4桁まで。少なくとも1つは正数にする。
    setup = _value(original, values, "SetupMinutes", 0)
    fixed = _value(original, values, "FixedMinutes", 0)
    per_unit = _value(original, values, "MinutesPerUnit", 0)
    priority = _value(original, values, "Priority", 1)
    _integer(setup, "準備時間")
    _integer(fixed, "固定時間")
    _integer(priority, "優先度", 1)
    # 浮動小数の丸め誤差を避けてDBのNUMERIC(12,4)の範囲と桁数を確認する。
    decimal_per_unit = Decimal(str(per_unit)) if per_unit is not None else None
    if (decimal_per_unit is None or not decimal_per_unit.is_finite()
            or decimal_per_unit < 0 or decimal_per_unit > Decimal("99999999.9999")
            or decimal_per_unit != decimal_per_unit.quantize(Decimal("0.0001"))):
        raise HTTPException(422, "単位当たり時間は0以上99999999.9999以下、小数点以下4桁以内で入力してください。")
    if setup + fixed + decimal_per_unit <= 0:
        raise HTTPException(422, "準備・固定・単位当たり時間のいずれかを0より大きくしてください。")

"""製品工程の段取り替え設定を検証し、所属拠点・重複・参照関係を保護する処理。"""
from typing import Any

from fastapi import HTTPException, Request
from sqlalchemy import false, or_, select, true
from sqlalchemy.orm import Session

from app.models.masters import Location, Product, ProductProcess, ProductSwitchRule, ProductSwitchTime, ResourceGroup
from app.services.product_validation import _integer, _name, _value


# 製品工程の一覧を、所属製品を経由して画面で選択中の拠点へ絞る。
def filter_product_process_list(statement, request: Request):
    # 工程は拠点IDを直接持たないため、製品との関連で検索する。
    location = request.query_params.get("locationId")
    if location is None:
        return statement
    try:
        location_id = int(location)
    except ValueError:
        raise HTTPException(422, "拠点IDは整数で指定してください。") from None
    return statement.join(Product, Product.ProductID == ProductProcess.ProductID).where(
        Product.LocationID == location_id, Product.DeleteFlag == false(),
    )


# 切替設定の拠点・対象グループ・既定時間と有効状態を確認する。
def validate_switch_time(db: Session, original: ProductSwitchTime | None, values: dict[str, Any]) -> None:
    _name(original, values, "ProductSwitchTimeName", "段取り替え設定名")
    # 既存明細の所属関係を変えないよう、登録後の拠点変更を拒否する。
    location_id = _value(original, values, "LocationID")
    if original is not None and location_id != original.LocationID:
        raise HTTPException(422, "登録済みの段取り替え設定の拠点は変更できません。")
    location = db.get(Location, location_id) if location_id is not None else None
    if location is None or location.DeleteFlag:
        raise HTTPException(422, "有効な拠点を指定してください。")
    # グループ未指定は拠点内の全設備。指定する場合は同じ拠点の有効なグループに限定する。
    group_id = _value(original, values, "ResourceGroupID")
    group = db.get(ResourceGroup, group_id) if group_id is not None else None
    if group_id is not None and (group is None or group.DeleteFlag or group.LocationID != location_id):
        raise HTTPException(422, "対象グループは同じ拠点の有効なグループを指定してください。")
    _integer(_value(original, values, "DefaultMinutes", 0), "既定の切替時間")
    # 有効な設定だけ、同じ設備へ適用される設定の重複を確認する。
    active = _value(original, values, "IsActive", True)
    if not isinstance(active, bool):
        raise HTTPException(422, "有効状態はtrueまたはfalseで指定してください。")
    if active:
        # 計算では設備ごとに一つの有効設定を選ぶため、全設備指定とグループ指定の重複も防ぐ。
        conflicts = select(ProductSwitchTime.ProductSwitchTimeID).where(
            ProductSwitchTime.LocationID == location_id, ProductSwitchTime.IsActive == true(),
        )
        if original is not None:
            conflicts = conflicts.where(ProductSwitchTime.ProductSwitchTimeID != original.ProductSwitchTimeID)
        if group_id is not None:
            conflicts = conflicts.where(or_(ProductSwitchTime.ResourceGroupID == group_id, ProductSwitchTime.ResourceGroupID.is_(None)))
        if db.scalar(conflicts.limit(1)) is not None:
            raise HTTPException(409, "対象設備に有効な段取り替え設定が重複します。既存設定を無効にするか、対象グループを変更してください。")


# 前後工程を同じ拠点へ限定し、任意指定を含む重複条件も保存前に検出する。
def validate_switch_rule(db: Session, original: ProductSwitchRule | None, values: dict[str, Any]) -> None:
    # 明細の親は変更せず、別の設定への移動は新規登録で行う。
    setting_id = _value(original, values, "ProductSwitchTimeID")
    if original is not None and setting_id != original.ProductSwitchTimeID:
        raise HTTPException(422, "登録済み明細の所属する段取り替え設定は変更できません。")
    setting = db.get(ProductSwitchTime, setting_id) if setting_id is not None else None
    if setting is None:
        raise HTTPException(422, "有効な段取り替え設定を指定してください。")
    # NULLは任意の工程。具体的な工程を指定した場合だけ存在と所属を検証する。
    before_id = _value(original, values, "FromProductProcessID")
    after_id = _value(original, values, "ToProductProcessID")
    for process_id in (before_id, after_id):
        if process_id is None:
            continue
        process = db.get(ProductProcess, process_id)
        product = db.get(Product, process.ProductID) if process is not None else None
        if product is None or product.DeleteFlag or product.LocationID != setting.LocationID:
            raise HTTPException(422, "切替前後の工程は同じ拠点の有効な製品工程を指定してください。")
    _integer(_value(original, values, "SetupMinutes", 0), "切替時間")
    if not isinstance(_value(original, values, "IsForbidden", False), bool):
        raise HTTPException(422, "禁止状態はtrueまたはfalseで指定してください。")
    # SQL Serverの一意制約に加え、NULL同士も同じ条件としてAPIで確認する。
    duplicate = db.scalar(select(ProductSwitchRule.ProductSwitchRuleID).where(
        ProductSwitchRule.ProductSwitchTimeID == setting_id,
        ProductSwitchRule.FromProductProcessID == before_id,
        ProductSwitchRule.ToProductProcessID == after_id,
    ).limit(1))
    if duplicate is not None and (original is None or duplicate != original.ProductSwitchRuleID):
        raise HTTPException(409, "同じ切替前・切替後の組合せが登録済みです。")


# 製品工程を削除する前に、前後どちらの段取り替え参照も確認する。
def switch_rule_using_process(db: Session, process_id: int) -> int | None:
    return db.scalar(select(ProductSwitchRule.ProductSwitchRuleID).where(or_(
        ProductSwitchRule.FromProductProcessID == process_id, ProductSwitchRule.ToProductProcessID == process_id,
    )).limit(1))

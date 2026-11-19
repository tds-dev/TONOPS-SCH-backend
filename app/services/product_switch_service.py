"""製品工程の段取り替え設定を検証し、所属拠点・重複・参照関係を保護する処理。"""
from typing import Any

from fastapi import HTTPException, Request
from sqlalchemy import and_, false, or_, select, true
from sqlalchemy.orm import Session

from app.models.masters import Location, Product, ProductProcess, ProductSwitchRule, ProductSwitchTime, Resource, ResourceGroup
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


# 切替設定の拠点・単体またはグループの対象・既定時間と有効状態を確認する。
def validate_switch_time(db: Session, original: ProductSwitchTime | None, values: dict[str, Any]) -> None:
    _name(original, values, "ProductSwitchTimeName", "段取り替え設定名")
    # 既存明細の所属関係を変えないよう、登録後の拠点変更を拒否する。
    location_id = _value(original, values, "LocationID")
    if original is not None and location_id != original.LocationID:
        raise HTTPException(422, "登録済みの段取り替え設定の拠点は変更できません。")
    location = db.get(Location, location_id) if location_id is not None else None
    if location is None or location.DeleteFlag:
        raise HTTPException(422, "有効な拠点を指定してください。")
    # 単体とグループの両方を未指定にした場合だけ、拠点内の全設備を対象とする。
    resource_id = _value(original, values, "ResourceID")
    group_id = _value(original, values, "ResourceGroupID")
    if resource_id is not None and group_id is not None:
        raise HTTPException(422, "対象リソースと対象グループは、どちらか一方だけを指定してください。")
    resource = db.get(Resource, resource_id) if resource_id is not None else None
    if resource_id is not None and (resource is None or resource.DeleteFlag or resource.LocationID != location_id):
        raise HTTPException(422, "対象リソースは同じ拠点の有効なリソースを指定してください。")
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
        # 全体・単体・グループの対象が重なる場合を拒否し、設備ごとに有効設定を1件に保つ。
        all_resources = and_(ProductSwitchTime.ResourceID.is_(None), ProductSwitchTime.ResourceGroupID.is_(None))
        if resource_id is not None:
            scopes = [all_resources, ProductSwitchTime.ResourceID == resource_id]
            if resource.ResourceGroupID is not None:
                scopes.append(ProductSwitchTime.ResourceGroupID == resource.ResourceGroupID)
            conflicts = conflicts.where(or_(*scopes))
        elif group_id is not None:
            members = select(Resource.ResourceID).where(Resource.ResourceGroupID == group_id, Resource.LocationID == location_id)
            conflicts = conflicts.where(or_(all_resources, ProductSwitchTime.ResourceGroupID == group_id,
                                            ProductSwitchTime.ResourceID.in_(members)))
        if db.scalar(conflicts.limit(1)) is not None:
            raise HTTPException(409, "対象リソースに有効な工程切替条件が重複します。既存設定を無効にするか、対象リソース・グループを変更してください。")


# 前後とも工程を限定しない禁止設定を、保存時と計算条件の読込時に共通で拒否する。
def validate_switch_rule_scope(before_id: int | None, after_id: int | None, forbidden: bool) -> None:
    if forbidden and before_id is None and after_id is None:
        raise HTTPException(422, "すべての工程どうしの順序は禁止できません。切替前または切替後の工程を指定してください。")


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
    # 部分更新では元の保存値も含めた最終状態で、禁止範囲を確認する。
    forbidden = _value(original, values, "IsForbidden", False)
    if not isinstance(forbidden, bool):
        raise HTTPException(422, "禁止状態はtrueまたはfalseで指定してください。")
    validate_switch_rule_scope(before_id, after_id, forbidden)
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

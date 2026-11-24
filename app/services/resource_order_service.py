"""リソース・リソースグループの表示順を1始まりの連番で保存・並べ替えする処理。"""
from typing import Any, TypeVar

from fastapi import HTTPException
from sqlalchemy import false, select
from sqlalchemy.orm import Session

from app.models.masters import Location, ProcessGroup, Resource, ResourceGroup
from app.services.calendar_service import validate_resource_location_write

# リソース・リソースグループ・工程区分の共通並び替え対象。
OrderedMaster = TypeVar("OrderedMaster", Resource, ResourceGroup, ProcessGroup)


# 同じ拠点の更新を直列化し、削除されていない対象行を現在の表示順で取得する。
def _locked_rows(db: Session, model: type[OrderedMaster], location_id: int | None) -> list[OrderedMaster]:
    # SQL Serverでは拠点行を更新用にロックし、同時更新による連番の崩れを防ぐ。
    location = db.scalar(
        select(Location)
        .where(Location.LocationID == location_id)
        .with_hint(Location, "WITH (UPDLOCK, HOLDLOCK)", dialect_name="mssql")
        .execution_options(populate_existing=True)
    ) if location_id is not None else None
    if location is None or location.DeleteFlag:
        raise HTTPException(422, "有効な拠点を指定してください。")
    pk_col = list(model.__table__.primary_key.columns)[0]
    return list(
        db.scalars(
            select(model)
            .where(model.LocationID == location_id, model.DeleteFlag == false())
            .order_by(model.SortOrder, pk_col)
            .execution_options(populate_existing=True)
        )
    )


# 表示順が1～上限の整数であることを確認し、0以下や不正値を拒否する。
def _validate_sort_order(value: Any, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise HTTPException(422, f"表示順は1～{maximum}の整数で指定してください。")
    return value


# 変更が発生した行だけ表示順と更新者を書き換え、未変更行の更新履歴を保つ。
def _assign_sort_orders(rows: list[OrderedMaster], user: str, start: int = 1) -> None:
    for number, row in enumerate(rows, start=start):
        if row.SortOrder != number:
            row.SortOrder = number
            row.UpdatedBy = user


# リソースまたはリソースグループの追加・更新を行い、表示順を1始まりの連番へ揃える。
def _save_ordered(
    db: Session,
    model: type[OrderedMaster],
    original: OrderedMaster | None,
    values: dict[str, Any],
    user: str,
    validate_extra=None,
) -> OrderedMaster:
    location_id = original.LocationID if original is not None else values.get("LocationID")
    if original is not None and "LocationID" in values and values["LocationID"] != original.LocationID:
        raise HTTPException(422, "登録済みデータの拠点は変更できません。")
    if values.get("DeleteFlag"):
        raise HTTPException(422, "削除するときは削除操作を使ってください。")
    rows = _locked_rows(db, model, location_id)
    if original is not None and original not in rows:
        raise HTTPException(404, "対象データは削除されています。一覧を再読込してください。")
    if validate_extra is not None:
        validate_extra(db, original, values)

    # 新規は末尾の次まで、編集は現在の件数までを許可する。
    maximum = len(rows) + (1 if original is None else 0)
    if original is None:
        target = _validate_sort_order(values.get("SortOrder", maximum), maximum)
        # 挿入位置より後ろの行を1つずつ繰り下げて連番を保つ。
        for index, row in enumerate(rows, start=1):
            new_order = index if index < target else index + 1
            if row.SortOrder != new_order:
                row.SortOrder = new_order
                row.UpdatedBy = user
        created = model(**{**values, "SortOrder": target}, CreatedBy=user)
        db.add(created)
        db.flush()
        return created

    if "SortOrder" in values:
        target = _validate_sort_order(values["SortOrder"], maximum)
        current_index = rows.index(original)
        # 対象行を移動先へ差し込み、拠点内の全有効行を1から振り直す。
        rows.pop(current_index)
        rows.insert(target - 1, original)
        _assign_sort_orders(rows, user)
    for key, value in values.items():
        if key != "SortOrder":
            setattr(original, key, value)
    original.UpdatedBy = user
    db.flush()
    return original


# 論理削除を実行し、残った有効行の表示順を1からの連番へ詰め直す。
def _delete_ordered(db: Session, model: type[OrderedMaster], original: OrderedMaster, user: str) -> None:
    rows = _locked_rows(db, model, original.LocationID)
    if original not in rows:
        raise HTTPException(404, "対象データは削除されています。一覧を再読込してください。")
    original.DeleteFlag = True
    original.UpdatedBy = user
    rows.remove(original)
    _assign_sort_orders(rows, user)
    db.flush()


# リソースの登録・更新時に、拠点・稼働上限時間・1始まりの表示順をまとめて処理する。
def save_resource(db: Session, original: Resource | None, values: dict[str, Any], user: str) -> Resource:
    return _save_ordered(db, Resource, original, values, user, validate_extra=validate_resource_location_write)


# リソースを論理削除し、同拠点の残りリソースの表示順を連番へ整える。
def delete_resource(db: Session, original: Resource, user: str) -> None:
    _delete_ordered(db, Resource, original, user)


# リソースグループの登録・更新時に、1始まりの表示順を連番として保存する。
def save_resource_group(
    db: Session, original: ResourceGroup | None, values: dict[str, Any], user: str
) -> ResourceGroup:
    return _save_ordered(db, ResourceGroup, original, values, user)


# リソースグループを論理削除し、同拠点の残りグループの表示順を連番へ整える。
def delete_resource_group(db: Session, original: ResourceGroup, user: str) -> None:
    _delete_ordered(db, ResourceGroup, original, user)

"""工程区分マスタの保存・並び替え・論理削除を行う処理。"""
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.masters import ProcessGroup, ProductProcess
from app.services.product_validation import _name, _value
from app.services.resource_order_service import _delete_ordered, _save_ordered


# 工程区分名の必須・文字数と、同じ拠点内での重複を確認する。
def _validate_process_group_write(
    db: Session, original: ProcessGroup | None, values: dict[str, Any]
) -> None:
    name = _name(original, values, "ProcessGroupName", "工程区分名")
    location_id = _value(original, values, "LocationID")
    # 削除済みも含め、同じ拠点内で工程区分名を重複させない。
    duplicate = db.scalar(
        select(ProcessGroup.ProcessGroupID).where(
            ProcessGroup.LocationID == location_id,
            ProcessGroup.ProcessGroupName == name,
        )
    )
    if duplicate is not None and (original is None or duplicate != original.ProcessGroupID):
        raise HTTPException(409, "同じ拠点で工程区分名が登録済みです。別の名称を入力してください。")


# 工程区分を登録・更新し、1始まりの表示順を連番に揃える。
def save_process_group(
    db: Session, original: ProcessGroup | None, values: dict[str, Any], user: str
) -> ProcessGroup:
    return _save_ordered(
        db, ProcessGroup, original, values, user, validate_extra=_validate_process_group_write
    )


# 製品工程から参照されていないことを確認し、論理削除後に表示順を詰め直す。
def delete_process_group(db: Session, original: ProcessGroup, user: str) -> None:
    used = db.scalar(
        select(ProductProcess.ProductProcessID)
        .where(ProductProcess.ProcessGroupID == original.ProcessGroupID)
        .limit(1)
    )
    if used is not None:
        raise HTTPException(409, "製品工程から参照されている工程区分は削除できません。先に工程の設定を変更してください。")
    _delete_ordered(db, ProcessGroup, original, user)

"""全テーブル共通の列（監査列、論理削除）。"""
from sqlalchemy import Boolean, Column

from app.core.timeutil import jst_now
from app.models.types import DateTime, String


class AuditMixin:
    """CreatedAt / CreatedBy / UpdatedAt / UpdatedBy（工程くんと同じ）。"""

    CreatedAt = Column(DateTime, nullable=False, default=jst_now)
    CreatedBy = Column(String(254), nullable=True)
    UpdatedAt = Column(DateTime, nullable=True, onupdate=jst_now)
    UpdatedBy = Column(String(254), nullable=True)


# 行を物理削除せず、一覧や計算の対象外にする削除フラグ。
class SoftDeleteMixin:
    DeleteFlag = Column(Boolean, nullable=False, default=False)


# APIの登録・更新入力から除外する、アプリが管理する履歴列。
AUDIT_COLUMNS = {"CreatedAt", "CreatedBy", "UpdatedAt", "UpdatedBy"}


def in_check(column: str, values: list[str]) -> str:
    """CHECK (col IN (...)) 制約の SQL 文字列。"""
    quoted = ",".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"

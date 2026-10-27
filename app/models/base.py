"""全テーブル共通の列（監査列、論理削除）。"""
from sqlalchemy import Boolean, Column, DateTime, String

from app.core.timeutil import utcnow


class AuditMixin:
    """CreatedAt / CreatedBy / UpdatedAt / UpdatedBy（工程くんと同じ）。"""

    CreatedAt = Column(DateTime, nullable=False, default=utcnow)
    CreatedBy = Column(String(254), nullable=True)
    UpdatedAt = Column(DateTime, nullable=True, onupdate=utcnow)
    UpdatedBy = Column(String(254), nullable=True)


class SoftDeleteMixin:
    DeleteFlag = Column(Boolean, nullable=False, default=False)


AUDIT_COLUMNS = {"CreatedAt", "CreatedBy", "UpdatedAt", "UpdatedBy"}


def in_check(column: str, values: list[str]) -> str:
    """CHECK (col IN (...)) 制約の SQL 文字列。"""
    quoted = ",".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"

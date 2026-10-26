"""Shared column sets used by every table (audit columns, logical delete)."""
from sqlalchemy import Boolean, Column, DateTime, String

from app.core.timeutil import utcnow


class AuditMixin:
    """CreatedAt / CreatedBy / UpdatedAt / UpdatedBy, as in 工程くん."""

    CreatedAt = Column(DateTime, nullable=False, default=utcnow)
    CreatedBy = Column(String(254), nullable=True)
    UpdatedAt = Column(DateTime, nullable=True, onupdate=utcnow)
    UpdatedBy = Column(String(254), nullable=True)


class SoftDeleteMixin:
    DeleteFlag = Column(Boolean, nullable=False, default=False)


AUDIT_COLUMNS = {"CreatedAt", "CreatedBy", "UpdatedAt", "UpdatedBy"}


def in_check(column: str, values: list[str]) -> str:
    """SQL text for a CHECK (col IN (...)) constraint."""
    quoted = ",".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"

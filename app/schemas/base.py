"""Pydantic schema helpers.

API JSON uses camelCase (`resourceName`) while models use PascalCase
(`ResourceName`). `ApiModel` converts automatically and accepts both on input.
`schemas_for(model)` builds Read / Create / Update schemas straight from a
SQLAlchemy model so the master-data CRUD stays in sync with the tables.
"""
import datetime as dt
from decimal import Decimal
from typing import Annotated, Any, Optional

from pydantic import AfterValidator, BaseModel, ConfigDict, PlainSerializer, create_model
from sqlalchemy import JSON, Boolean, Date, DateTime, Float, Integer, Numeric, String, Text, Time
from sqlalchemy.types import TypeEngine

from app.models.base import AUDIT_COLUMNS


def _to_naive_utc(value: dt.datetime) -> dt.datetime:
    if value.tzinfo is not None:
        value = value.astimezone(dt.timezone.utc).replace(tzinfo=None)
    return value


def _iso_utc(value: dt.datetime) -> str:
    return value.isoformat() + "Z" if value.tzinfo is None else value.isoformat()


# Stored naive UTC; accepted with any offset; returned as "...Z".
UtcDatetime = Annotated[
    dt.datetime,
    AfterValidator(_to_naive_utc),
    PlainSerializer(_iso_utc, return_type=str, when_used="json"),
]


def to_camel(name: str) -> str:
    """'ResourceName' -> 'resourceName', 'SiteID' -> 'siteID' -> 'siteId'."""
    if not name:
        return name
    out = name[0].lower() + name[1:]
    if out.endswith("ID"):
        out = out[:-2] + "Id"
    return out


class ApiModel(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel,
    )


def python_type(col_type: TypeEngine) -> Any:
    """Map a SQLAlchemy column type to the Python type used in the API."""
    if isinstance(col_type, Boolean):
        return bool
    if isinstance(col_type, Integer):  # also BigInteger / SmallInteger
        return int
    if isinstance(col_type, (Numeric, Float)):
        return float
    if isinstance(col_type, DateTime):
        return UtcDatetime
    if isinstance(col_type, Date):
        return dt.date
    if isinstance(col_type, Time):
        return dt.time
    if isinstance(col_type, JSON):
        return Any
    if isinstance(col_type, (String, Text)):
        return str
    try:
        return col_type.python_type
    except NotImplementedError:
        return Any


_cache: dict[type, tuple[type[ApiModel], type[ApiModel], type[ApiModel]]] = {}


def schemas_for(model: type) -> tuple[type[ApiModel], type[ApiModel], type[ApiModel]]:
    """Return (Read, Create, Update) Pydantic models for a SQLAlchemy model."""
    if model in _cache:
        return _cache[model]
    read_fields: dict[str, Any] = {}
    create_fields: dict[str, Any] = {}
    update_fields: dict[str, Any] = {}
    single_pk = len(model.__table__.primary_key.columns) == 1
    for col in model.__table__.columns:
        name = col.key
        py = python_type(col.type)
        read_fields[name] = (Optional[py], None)
        # Surrogate identity keys are server-generated; composite keys stay writable.
        is_identity = col.primary_key and single_pk and py is int
        if is_identity or name in AUDIT_COLUMNS or name == "RowVer":
            continue
        has_default = col.default is not None or col.server_default is not None
        if col.nullable or has_default:
            create_fields[name] = (Optional[py], None)
        else:
            create_fields[name] = (py, ...)
        update_fields[name] = (Optional[py], None)
    read = create_model(f"{model.__name__}Read", __base__=ApiModel, **read_fields)
    create = create_model(f"{model.__name__}Create", __base__=ApiModel, **create_fields)
    update = create_model(f"{model.__name__}Update", __base__=ApiModel, **update_fields)
    _cache[model] = (read, create, update)
    return _cache[model]


def coerce(value: Any) -> Any:
    """Decimal -> float for responses built by hand."""
    return float(value) if isinstance(value, Decimal) else value

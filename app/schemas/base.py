"""Pydantic スキーマの補助。

API の JSON は camelCase（`resourceName`）、モデルは PascalCase（`ResourceName`）。
`ApiModel` が自動で変換し、入力はどちらの形式も受け付ける。
`schemas_for(model)` は SQLAlchemy モデルから Read / Create / Update スキーマを
直接生成する。APIの項目名はアプリ側の属性名を使い、DB上の旧列名と分離する。
"""
import datetime as dt
from decimal import Decimal
from typing import Annotated, Any, Optional

from pydantic import AfterValidator, BaseModel, ConfigDict, PlainSerializer, create_model
from sqlalchemy import JSON, Boolean, Date, DateTime, Float, Integer, Numeric, String, Text, Time, inspect
from sqlalchemy.types import TypeEngine

from app.models.base import AUDIT_COLUMNS


def _to_naive_utc(value: dt.datetime) -> dt.datetime:
    if value.tzinfo is not None:
        value = value.astimezone(dt.timezone.utc).replace(tzinfo=None)
    return value


def _iso_utc(value: dt.datetime) -> str:
    return value.isoformat() + "Z" if value.tzinfo is None else value.isoformat()


# 保存は naive な UTC。入力は任意のオフセット可。出力は "...Z"。
UtcDatetime = Annotated[
    dt.datetime,
    AfterValidator(_to_naive_utc),
    PlainSerializer(_iso_utc, return_type=str, when_used="json"),
]


def to_camel(name: str) -> str:
    """'ResourceName' -> 'resourceName', 'SiteID' -> 'siteId', 'start_at' -> 'startAt'."""
    if not name:
        return name
    if "_" in name:
        head, *rest = name.split("_")
        out = head + "".join(p[:1].upper() + p[1:] for p in rest)
    else:
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
    """SQLAlchemy の列型を API で使う Python の型に対応付ける。"""
    if isinstance(col_type, Boolean):
        return bool
    if isinstance(col_type, Integer):  # BigInteger / SmallInteger も含む
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
    """SQLAlchemy モデルから (Read, Create, Update) の Pydantic モデルを返す。"""
    if model in _cache:
        return _cache[model]
    read_fields: dict[str, Any] = {}
    create_fields: dict[str, Any] = {}
    update_fields: dict[str, Any] = {}
    single_pk = len(model.__table__.primary_key.columns) == 1
    # モデル属性名から、orderId等のAPI項目を生成する。
    for attribute in inspect(model).column_attrs:
        col = attribute.columns[0]
        name = attribute.key
        py = python_type(col.type)
        read_fields[name] = (Optional[py], None)
        # 代理キー（自動採番）はサーバー側で生成。複合キーは書込み可のまま。
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
    """手組みのレスポンス用に Decimal を float に変換する。"""
    return float(value) if isinstance(value, Decimal) else value

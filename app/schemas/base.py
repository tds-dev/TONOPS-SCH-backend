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


# API入力と出力に共通の日本時間処理を使い、変換の重複を避ける。
from app.core.timeutil import as_jst, to_jst_naive


# APIへ返す日時に、日本時間を示す+09:00を付ける。
def _iso_jst(value: dt.datetime) -> str:
    return as_jst(value).isoformat()


# 保存は時差情報なしの日本時間。API出力は+09:00付きとする。
JstDatetime = Annotated[
    dt.datetime,
    AfterValidator(to_jst_naive),
    PlainSerializer(_iso_jst, return_type=str, when_used="json"),
]


def to_camel(name: str) -> str:
    """'ResourceName' -> 'resourceName', 'LocationID' -> 'locationId', 'start_at' -> 'startAt'."""
    if not name:
        return name
    # WBSのような大文字略語を、画面で使うwbsNumberへ揃える。
    if name.startswith("WBS"):
        return "wbs" + name[3:]
    if "_" in name:
        head, *rest = name.split("_")
        out = head + "".join(p[:1].upper() + p[1:] for p in rest)
    else:
        out = name[0].lower() + name[1:]
    if out.endswith("ID"):
        out = out[:-2] + "Id"
    return out


# API項目名の変換とモデルからの読み取りを共通化する基底の型。
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
        return JstDatetime
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

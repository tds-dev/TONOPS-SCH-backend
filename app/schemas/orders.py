"""オーダー本体の自動生成スキーマに、複数作業者の入出力を追加する。"""
from typing import Annotated

from pydantic import ConfigDict, Field

from app.models.transactions import Order
from app.schemas.base import schemas_for

# DB列の型・必須項目を共通処理から引き継ぎ、オーダー専用の項目だけを追加する。
BaseRead, BaseCreate, BaseUpdate = schemas_for(Order)
# boolや小数・文字列を作業者IDとして受け付けず、正の整数だけを許可する。
WorkerId = Annotated[int, Field(strict=True, gt=0)]


class OrderRead(BaseRead):  # type: ignore[misc, valid-type]
    """中間テーブルの作業者IDを、本体とまとめて返す。"""

    worker_ids: list[int] = Field(default_factory=list)


class OrderCreate(BaseCreate):  # type: ignore[misc, valid-type]
    """未指定は空配列。旧workerIdなどの未対応項目は入力エラーにする。"""

    model_config = ConfigDict(extra="forbid")
    worker_ids: list[WorkerId] = Field(default_factory=list)


class OrderUpdate(BaseUpdate):  # type: ignore[misc, valid-type]
    """未送信なら指定を維持し、空配列を送信したときだけ全解除する。"""

    model_config = ConfigDict(extra="forbid")
    worker_ids: list[WorkerId] = Field(default_factory=list)

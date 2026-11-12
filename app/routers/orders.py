"""オーダー・タスクの管理と、製品マスタから組み立てる設備候補・前後関係の参照API。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.transactions import Order, Task
from app.routers.crud import crud_router
from app.routers.deps import current_user
from app.schemas.base import ApiModel, schemas_for
from app.services.order_service import generate_tasks
from app.services.order_validation import validate_order_write
from app.services.task_conditions import build_task_conditions

# 保存済みタスクをAPIへ返す型。
TaskRead, _, _ = schemas_for(Task)


# 製品工程の候補を、オーダー数量で計算して返す読取専用の項目。
class OptionRead(ApiModel):
    # 表示用の候補IDは、元の工程設備候補の識別番号。
    option_id: int
    resource_id: int | None
    resource_group_id: int | None
    # 所要時間は固定準備を含み、準備時間はその内訳として返す。
    duration_min: int
    setup_minutes: int
    priority: int


# 製品工程の順序と待ち時間から組み立てる、保存しない前後関係。
class DependencyRead(ApiModel):
    # 表示用の識別値として後続タスクIDを返す。DBの行IDではない。
    dependency_id: int
    predecessor_task_id: int
    successor_task_id: int
    # 工程マスタから作る関係はFSのみ。最大待ち時間の未指定は上限なし。
    dependency_type: str
    lag_min: int
    max_lag_min: int | None


# タスクに実行できる設備候補を含めて返す。
class TaskWithOptions(TaskRead):  # type: ignore[misc, valid-type]
    # 保存列に加え、現在のマスタから得た設備候補を返す。
    options: list[OptionRead] = []  # type: ignore[valid-type]


# 生成直後と詳細取得で、同じ計算方法・応答形式を使う。
def tasks_with_options(db: Session, tasks: list[Task]) -> list[TaskWithOptions]:
    # タスク本体の保存情報と、保存しない設備候補を結合する。
    conditions = build_task_conditions(db, tasks)
    return [TaskWithOptions(**TaskRead.model_validate(task).model_dump(),
                            options=conditions.options[task.TaskID]) for task in tasks]


# タスク生成と詳細取得をまとめる追加API。
order_extra = APIRouter(prefix="/orders", tags=["Orders"])


@order_extra.post("/{order_id}/generate-tasks", response_model=list[TaskWithOptions])
def post_generate_tasks(
    order_id: int,
    replace: bool = False,
    db: Session = Depends(get_db),
    user: str = Depends(current_user),
):
    """タスクだけを保存し、設備候補は現在の製品マスタから計算して返す。"""
    # 削除済みのオーダーから新たなタスクを作らない。
    order = db.get(Order, order_id)
    if order is None or order.DeleteFlag:
        raise HTTPException(404, f"Order {order_id} not found")
    return tasks_with_options(db, generate_tasks(db, order, user, replace=replace))


@order_extra.get("/{order_id}/tasks", response_model=list[TaskWithOptions])
def get_order_tasks(order_id: int, db: Session = Depends(get_db)):
    """タスク本体と、製品マスタから求めた現在の設備候補を返す。"""
    # 保存したタスクの表示順・作業状態は維持する。
    tasks = db.scalars(select(Task).where(Task.OrderID == order_id).order_by(Task.Sequence)).all()
    return tasks_with_options(db, tasks)


@order_extra.get("/{order_id}/dependencies", response_model=list[DependencyRead])
def get_order_dependencies(order_id: int, db: Session = Depends(get_db)):
    """指定オーダーの前後関係を現在の製品工程順と待ち時間から組み立てる。"""
    # タスクIDを維持し、マスタの並べ替え・待ち時間の編集をそのまま反映する。
    tasks = db.scalars(select(Task).where(Task.OrderID == order_id)).all()
    return build_task_conditions(db, tasks).dependencies


# オーダーだけに追加の入力確認を適用し、他のCRUDは従来どおり登録する。
routers = [
    order_extra,  # /orders/{id}/tasks が隠れないよう先に登録する
    crud_router(Order, "/orders", "Orders", order_by="DeadLine", validate_write=validate_order_write),
    crud_router(Task, "/tasks", "Orders", order_by="Sequence"),
]

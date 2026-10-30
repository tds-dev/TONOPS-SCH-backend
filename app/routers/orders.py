"""オーダー、タスク、依存関係。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.transactions import Order, Task, TaskDependency, TaskResourceOption
from app.routers.crud import crud_router
from app.routers.deps import current_user
from app.schemas.base import schemas_for
from app.services.order_service import generate_tasks

TaskRead, _, _ = schemas_for(Task)
OptionRead, _, _ = schemas_for(TaskResourceOption)
DependencyRead, _, _ = schemas_for(TaskDependency)


class TaskWithOptions(TaskRead):  # type: ignore[misc, valid-type]
    options: list[OptionRead] = []  # type: ignore[valid-type]


order_extra = APIRouter(prefix="/orders", tags=["Orders"])


@order_extra.post("/{order_id}/generate-tasks", response_model=list[TaskWithOptions])
def post_generate_tasks(
    order_id: int,
    replace: bool = False,
    db: Session = Depends(get_db),
    user: str = Depends(current_user),
):
    """オーダーの工程ルートを展開し、タスク・リソース候補・依存関係を作成する。"""
    order = db.get(Order, order_id)
    if order is None or order.DeleteFlag:
        raise HTTPException(404, f"Order {order_id} not found")
    return generate_tasks(db, order, user, replace=replace)


@order_extra.get("/{order_id}/tasks", response_model=list[TaskWithOptions])
def get_order_tasks(order_id: int, db: Session = Depends(get_db)):
    return db.scalars(select(Task).where(Task.OrderID == order_id).order_by(Task.Sequence)).all()


@order_extra.get("/{order_id}/dependencies", response_model=list[DependencyRead])
def get_order_dependencies(order_id: int, db: Session = Depends(get_db)):
    task_ids = select(Task.TaskID).where(Task.OrderID == order_id)
    return db.scalars(
        select(TaskDependency)
        .where(TaskDependency.SuccessorTaskID.in_(task_ids))
        .order_by(TaskDependency.DependencyID)
    ).all()


routers = [
    order_extra,  # /orders/{id}/tasks が隠れないよう先に登録する
    crud_router(Order, "/orders", "Orders", order_by="DueAt"),
    crud_router(Task, "/tasks", "Orders", order_by="Sequence"),
    crud_router(TaskResourceOption, "/task-resource-options", "Orders"),
    crud_router(TaskDependency, "/dependencies", "Orders"),
]

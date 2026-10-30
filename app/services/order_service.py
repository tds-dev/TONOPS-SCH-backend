"""オーダーをスケジュール可能なタスクに変換する。

`generate_tasks` はオーダーの工程ルート（またはその製品の既定ルート）を展開し、
T_Tasks、T_TaskResourceOptions、連続するタスク間の FS 依存関係を作成する。
タスク属性 = 製品属性を工程属性、さらにオーダー属性で上書きしたもの。
これにより {"family": "A"} のようなルールのセレクターがタスクに効く。
"""
import math

from fastapi import HTTPException, status
from sqlalchemy import delete, false, select
from sqlalchemy.orm import Session

from app.models.masters import Product, Routing
from app.models.transactions import Order, PlanAssignment, Task, TaskDependency, TaskResourceOption


def option_duration(setup: int, fixed: int, minutes_per_unit: float, quantity: float) -> int:
    """所要時間（整数分）= 段取り + 固定 + 数量 × 単位当たり時間。"""
    run = round(float(quantity or 0) * float(minutes_per_unit or 0), 6)  # 0.1 × 1200 = 120.000…01
    return int(setup + fixed + math.ceil(run))


# オーダー指定の工程ルートを優先し、未指定なら製品の既定ルートか最新版を取得する。
def resolve_routing(db: Session, order: Order) -> Routing:
    if order.RoutingID:
        routing = db.get(Routing, order.RoutingID)
    elif order.ProductID:
        routing = db.scalars(
            select(Routing)
            .where(Routing.ProductID == order.ProductID, Routing.DeleteFlag == false())
            .order_by(Routing.IsDefault.desc(), Routing.Revision.desc())
        ).first()
    else:
        routing = None
    if routing is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Order {order.OrderNo} has no routing (set RoutingID or a product with a routing).",
        )
    return routing


# 工程ルートの定義から、オーダーごとのタスク・実行候補・前後関係を生成する。
def generate_tasks(db: Session, order: Order, user: str, replace: bool = False) -> list[Task]:
    existing = db.scalars(select(Task).where(Task.OrderID == order.OrderID)).all()
    if existing:
        if not replace:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"Order {order.OrderNo} already has {len(existing)} tasks; pass replace=true to rebuild.",
            )
        task_ids = [t.TaskID for t in existing]
        used = db.scalars(
            select(PlanAssignment.TaskID).where(PlanAssignment.TaskID.in_(task_ids)).limit(1)
        ).first()
        if used is not None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"Order {order.OrderNo} tasks are used in a plan; they cannot be rebuilt.",
            )
        db.execute(
            delete(TaskDependency).where(
                TaskDependency.PredecessorTaskID.in_(task_ids)
                | TaskDependency.SuccessorTaskID.in_(task_ids)
            )
        )
        for t in existing:
            db.delete(t)
        db.flush()

    # 元にする工程ルートと製品を取得し、属性と数量を生成するタスクへ引き継ぐ。
    routing = resolve_routing(db, order)
    product = db.get(Product, routing.ProductID)
    base_attrs = dict(product.AttributesJSON or {}) if product else {}
    qty = float(order.Quantity or 0)

    tasks: list[Task] = []
    for seq, step in enumerate(routing.steps, start=1):
        attrs = {**base_attrs, **(step.AttributesJSON or {}), **(order.AttributesJSON or {})}
        task = Task(
            OrderID=order.OrderID,
            RoutingStepID=step.RoutingStepID,
            TaskNo=str(step.StepNo),
            TaskName=step.StepName,
            Sequence=seq,
            Status="NOT_STARTED",
            AttributesJSON=attrs,
            CreatedBy=user,
        )
        for sr in step.resources:
            task.options.append(
                TaskResourceOption(
                    ResourceID=sr.ResourceID,
                    ResourceGroupID=sr.ResourceGroupID,
                    DurationMin=option_duration(
                        sr.SetupMinutes, sr.FixedMinutes, sr.MinutesPerUnit, qty
                    ),
                    SetupMinutes=sr.SetupMinutes,
                    Priority=sr.Priority,
                    CreatedBy=user,
                )
            )
        db.add(task)
        tasks.append(task)
    db.flush()

    steps = list(routing.steps)
    for i in range(1, len(tasks)):
        prev_step = steps[i - 1]
        db.add(
            TaskDependency(
                PredecessorTaskID=tasks[i - 1].TaskID,
                SuccessorTaskID=tasks[i].TaskID,
                DependencyType="FS",
                LagMin=prev_step.MinLagAfterMin or 0,
                MaxLagMin=prev_step.MaxLagAfterMin,
                CreatedBy=user,
            )
        )
    if order.RoutingID is None:
        order.RoutingID = routing.RoutingID
    db.commit()
    for t in tasks:
        db.refresh(t)
    return tasks

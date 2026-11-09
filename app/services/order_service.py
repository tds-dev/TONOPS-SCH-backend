"""オーダーをスケジュール可能なタスクに変換する。

`generate_tasks` はオーダーの製品に直接登録された工程を展開し、
T_Tasks、T_TaskResourceOptions、連続するタスク間の FS 依存関係を作成する。
タスク属性はオーダー属性を引き継ぐ。製品・工程には属性を持たせない。
これにより {"family": "A"} のようなルールのセレクターがタスクに効く。
"""
import math

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.masters import Product, ProductProcess
from app.models.transactions import Actual, Order, PlanAssignment, Task, TaskDependency, TaskResourceOption


def option_duration(setup: int, fixed: int, minutes_per_unit: float, quantity: float) -> int:
    """所要時間（整数分）= 段取り + 固定 + 数量 × 単位当たり時間。"""
    run = round(float(quantity or 0) * float(minutes_per_unit or 0), 6)  # 0.1 × 1200 = 120.000…01
    return int(setup + fixed + math.ceil(run))


# オーダーと同じ拠点の有効な製品から、工程を実行順で取得する。
def resolve_product_processes(db: Session, order: Order) -> list[ProductProcess]:
    # タスク生成の対象製品。未指定や削除済みでは新しいタスクを作らない。
    product = db.get(Product, order.ProductID) if order.ProductID is not None else None
    if product is None or product.DeleteFlag or product.LocationID != order.LocationID:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "タスク生成には同じ拠点の有効な製品を指定してください。")
    # 工程番号で並べた製品固有の工程。製品に工程がない場合は登録を案内する。
    processes = db.scalars(select(ProductProcess).where(
        ProductProcess.ProductID == product.ProductID,
    ).order_by(ProductProcess.SequenceNumber)).all()
    if not processes:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "この製品には工程が登録されていません。製品・工程画面で工程を登録してください。")
    return processes


# 製品工程の定義から、オーダーごとのタスク・実行候補・前後関係を生成する。
def generate_tasks(db: Session, order: Order, user: str, replace: bool = False) -> list[Task]:
    # 入力不備で既存タスクを削除しないよう、先に生成元の工程を確認する。
    processes = resolve_product_processes(db, order)
    # 生成済みタスク。再生成時は計画・実績・作業開始の有無を先に確認する。
    existing = db.scalars(select(Task).where(Task.OrderID == order.OrderID)).all()
    if existing:
        if not replace:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"Order {order.OrderNo} already has {len(existing)} tasks; pass replace=true to rebuild.",
            )
        # 再生成対象のタスク番号と、既存計画からの参照。
        task_ids = [t.TaskID for t in existing]
        used = db.scalars(
            select(PlanAssignment.TaskID).where(PlanAssignment.TaskID.in_(task_ids)).limit(1)
        ).first()
        if used is not None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"Order {order.OrderNo} tasks are used in a plan; they cannot be rebuilt.",
            )
        if (any(task.Status != "NOT_STARTED" for task in existing)
                or db.scalar(select(Actual.ActualID).where(Actual.TaskID.in_(task_ids)).limit(1)) is not None):
            raise HTTPException(status.HTTP_409_CONFLICT, "作業開始・実績登録済みのタスクは再生成できません。")
        db.execute(
            delete(TaskDependency).where(
                TaskDependency.PredecessorTaskID.in_(task_ids)
                | TaskDependency.SuccessorTaskID.in_(task_ids)
            )
        )
        for t in existing:
            db.delete(t)
        db.flush()

    # オーダーの数量を所要時間計算へ使う。
    qty = float(order.Quantity or 0)

    # 工程番号順に作るタスク。属性はオーダーから複製する。
    tasks: list[Task] = []
    for seq, process in enumerate(processes, start=1):
        # この工程に対応するオーダー固有のタスク。
        task = Task(
            OrderID=order.OrderID,
            ProductProcessID=process.ProductProcessID,
            TaskNo=str(process.SequenceNumber),
            TaskName=process.ProcessName,
            Sequence=seq,
            Status="NOT_STARTED",
            AttributesJSON=dict(order.AttributesJSON or {}),
            CreatedBy=user,
        )
        for sr in process.resources:
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

    # 前工程の終了から次工程の開始までの待ち時間を引き継ぐ。
    for i in range(1, len(tasks)):
        prev_process = processes[i - 1]
        db.add(
            TaskDependency(
                PredecessorTaskID=tasks[i - 1].TaskID,
                SuccessorTaskID=tasks[i].TaskID,
                DependencyType="FS",
                LagMin=prev_process.MinLagAfterMin or 0,
                MaxLagMin=prev_process.MaxLagAfterMin,
                CreatedBy=user,
            )
        )
    db.commit()
    for t in tasks:
        db.refresh(t)
    return tasks

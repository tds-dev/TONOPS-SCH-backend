"""オーダーをスケジュール可能なタスクに変換する。

`generate_tasks` はオーダーの製品に直接登録された工程をT_Tasksへ展開する。
設備候補・所要時間・工程間の待ち時間は、保存せず利用時に製品マスタから組み立てる。
タスク属性はオーダー属性を引き継ぐ。製品・工程には属性を持たせない。
これにより {"family": "A"} のようなルールのセレクターがタスクに効く。
"""
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.masters import Product, ProductProcess
from app.models.transactions import WorkActual, Order, PlanAssignment, Task


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


# 製品工程の定義から、計画・進捗・実績で共用するオーダーごとのタスクだけを生成する。
def generate_tasks(db: Session, order: Order, user: str, replace: bool = False) -> list[Task]:
    # 入力不備で既存タスクを削除しないよう、先に生成元の工程を確認する。
    processes = resolve_product_processes(db, order)
    # 生成済みタスク。再生成時は計画・実績・作業開始の有無を先に確認する。
    existing = db.scalars(select(Task).where(Task.OrderID == order.OrderID)).all()
    if existing:
        if not replace:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"Order {order.WBSNumber} already has {len(existing)} tasks; pass replace=true to rebuild.",
            )
        # 再生成対象のタスク番号と、既存計画からの参照。
        task_ids = [t.TaskID for t in existing]
        used = db.scalars(
            select(PlanAssignment.TaskID).where(PlanAssignment.TaskID.in_(task_ids)).limit(1)
        ).first()
        if used is not None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"Order {order.WBSNumber} tasks are used in a plan; they cannot be rebuilt.",
            )
        if (any(task.Status != "NOT_STARTED" for task in existing)
                or db.scalar(select(WorkActual.WorkActualID).where(WorkActual.TaskID.in_(task_ids)).limit(1)) is not None):
            raise HTTPException(status.HTTP_409_CONFLICT, "作業開始・実績登録済みのタスクは再生成できません。")
        for t in existing:
            db.delete(t)
        db.flush()

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
        db.add(task)
        tasks.append(task)
    db.flush()

    db.commit()
    for t in tasks:
        db.refresh(t)
    return tasks

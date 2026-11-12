"""製品工程マスタとオーダー数量から、保存しない設備候補・工程間の条件を組み立てる。"""
import math
from dataclasses import dataclass, field

from sqlalchemy import false, select
from sqlalchemy.orm import Session, selectinload

from app.core.db import chunks
from app.models.masters import ProductProcess
from app.models.transactions import Order, Task


# タスクに使える設備候補。option_idは保存行ではなく、元の工程設備候補のID。
@dataclass
class TaskOption:
    # 元の候補と、個別設備または設備グループの識別番号。
    option_id: int
    resource_id: int | None
    resource_group_id: int | None
    # 固定準備を含む所要時間、内訳の準備時間、元マスタの優先度。
    duration_min: int
    setup_minutes: int
    priority: int


# 同一オーダーの連続する製品工程を結ぶ、計算時だけの前後関係。
@dataclass
class TaskLink:
    # 後続タスクIDを画面用の識別値に使う。DBの自動採番ではない。
    dependency_id: int
    predecessor_task_id: int
    successor_task_id: int
    # 製品工程の順序は、終了から開始までのFS関係として扱う。
    dependency_type: str
    lag_min: int
    max_lag_min: int | None


# 計算と画面表示で共用する、タスク別候補と前後関係の一覧。
@dataclass
class TaskConditions:
    # タスクIDをキーに、候補がないタスクも空の一覧として保持する。
    options: dict[int, list[TaskOption]] = field(default_factory=dict)
    dependencies: list[TaskLink] = field(default_factory=list)
    # 工程追加後など、作業本体がまだ揃っていないオーダーを計算前に通知する。
    errors: list[str] = field(default_factory=list)


# 準備＋固定＋数量×単位当たり時間を、整数分へ切り上げて求める。
def option_duration(setup: int, fixed: int, minutes_per_unit: float, quantity: float) -> int:
    # 小数の計算誤差で、ちょうどの分数が余分に切り上がることを防ぐ。
    run = round(float(quantity or 0) * float(minutes_per_unit or 0), 6)
    return int(setup + fixed + math.ceil(run))


# 最新の製品工程をまとめて読み込み、タスク用テーブルへの複製を行わず条件を作る。
def build_task_conditions(db: Session, tasks: list[Task]) -> TaskConditions:
    # 呼出し元が指定したタスクだけに候補・関係を返す。
    result = TaskConditions(options={task.TaskID: [] for task in tasks})
    if not tasks:
        return result

    # SQL Serverのパラメーター上限を超えない件数で、所属オーダーを読み込む。
    orders: dict[int, Order] = {}
    for batch in chunks({task.OrderID for task in tasks}):
        orders.update((order.OrderID, order) for order in db.scalars(
            select(Order).where(Order.OrderID.in_(batch))
        ))

    # 工程と設備候補は毎回再読込し、同じセッション内のマスタ編集も反映する。
    processes: dict[int, ProductProcess] = {}
    by_product: dict[int, list[ProductProcess]] = {}
    for batch in chunks({order.ProductID for order in orders.values() if order.ProductID is not None}):
        rows = db.scalars(
            select(ProductProcess).where(ProductProcess.ProductID.in_(batch))
            .options(selectinload(ProductProcess.resources)).execution_options(populate_existing=True)
            .order_by(ProductProcess.SequenceNumber, ProductProcess.ProductProcessID)
        ).all()
        for process in rows:
            processes[process.ProductProcessID] = process
            by_product.setdefault(process.ProductID, []).append(process)

    # 完了済み・対象外の作業も含めて生成済み工程を確認し、未生成の工程だけを区別する。
    generated: dict[int, set[int]] = {}
    for batch in chunks(orders):
        for order_id, process_id in db.execute(select(Task.OrderID, Task.ProductProcessID).where(
            Task.OrderID.in_(batch), Task.IsSummary == false(), Task.ProductProcessID.is_not(None),
        )):
            generated.setdefault(order_id, set()).add(process_id)
    for order_id, order in orders.items():
        missing = [process.ProcessName for process in by_product.get(order.ProductID, [])
                   if process.ProductProcessID not in generated.get(order_id, set())]
        if missing:
            result.errors.append(f"{order.WBSNumber}: 未生成の工程があります（{'、'.join(missing)}）。タスク生成を確認してください。")

    # 別オーダーや別製品の工程を結ばないよう、オーダーと工程IDの組でタスクを管理する。
    by_order: dict[int, dict[int, Task]] = {}
    for task in tasks:
        order = orders.get(task.OrderID)
        process = processes.get(task.ProductProcessID)
        if order is None or process is None or process.ProductID != order.ProductID:
            continue
        by_order.setdefault(task.OrderID, {})[process.ProductProcessID] = task
        result.options[task.TaskID] = [
            TaskOption(
                option_id=candidate.ProductProcessResourceID,
                resource_id=candidate.ResourceID, resource_group_id=candidate.ResourceGroupID,
                duration_min=option_duration(candidate.SetupMinutes, candidate.FixedMinutes,
                                             candidate.MinutesPerUnit, order.Quantity),
                setup_minutes=candidate.SetupMinutes, priority=candidate.Priority,
            )
            for candidate in sorted(process.resources, key=lambda row: row.ProductProcessResourceID)
        ]

    # 工程番号で隣り合う工程だけを結ぶ。対象外・未生成の中間工程を飛び越えて結ばない。
    for order_id, mapped_tasks in sorted(by_order.items()):
        ordered = by_product.get(orders[order_id].ProductID, [])
        for previous, following in zip(ordered, ordered[1:]):
            predecessor = mapped_tasks.get(previous.ProductProcessID)
            successor = mapped_tasks.get(following.ProductProcessID)
            if predecessor is None or successor is None:
                continue
            result.dependencies.append(TaskLink(
                dependency_id=successor.TaskID,
                predecessor_task_id=predecessor.TaskID, successor_task_id=successor.TaskID,
                dependency_type="FS", lag_min=previous.MinLagAfterMin or 0,
                max_lag_min=previous.MaxLagAfterMin,
            ))
    return result

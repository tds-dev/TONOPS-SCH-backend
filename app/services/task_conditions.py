"""製品工程マスタとオーダー数量から、保存しない設備候補・工程間の条件を組み立てる。"""
import math
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.db import chunks
from app.models.masters import ProductProcess
from app.models.transactions import Order, Task
from app.services.product_validation import validate_weekday_settings


# タスクに使える設備候補。option_idは保存行ではなく、元の工程設備候補のID。
@dataclass
class TaskOption:
    # 元の候補と、個別設備または設備グループの識別番号。
    option_id: int
    resource_id: int | None
    resource_group_id: int | None
    # 固定準備を含む所要時間と、内訳の準備時間。
    duration_min: int
    setup_minutes: int


# リソース未登録でも返せる、工程とオーダー数量から求めた作業時間。
@dataclass
class TaskTiming:
    duration_min: int
    setup_minutes: int


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


# 工程の曜日設定を、DBへの追加問合せなしで計算へ引き渡す。
@dataclass
class TaskWeekdayRestriction:
    # 工程で許可する曜日と、この曜日制限だけの有効状態。
    weekdays: list[int]
    enabled: bool
    # 計画開始日時と比較する日本時間の適用期間。None側は制限なし。
    start_at: datetime | None
    end_at: datetime | None

    # 計画開始日時に有効な許可曜日を返し、無効・期間外なら制限を外す。
    def allowed_at(self, plan_start: datetime) -> list[int] | None:
        if not self.enabled or (self.start_at is not None and plan_start < self.start_at):
            return None
        if self.end_at is not None and plan_start > self.end_at:
            return None
        return self.weekdays


# 計算と画面表示で共用する、タスク別候補・曜日設定と前後関係の一覧。
@dataclass
class TaskConditions:
    # タスクIDをキーに、候補がないタスクも空の一覧として保持する。
    options: dict[int, list[TaskOption]] = field(default_factory=dict)
    # 工程を特定できたタスクの共通作業時間。設備候補の件数に依存しない。
    timings: dict[int, TaskTiming] = field(default_factory=dict)
    dependencies: list[TaskLink] = field(default_factory=list)
    # タスクごとの最新工程設定。作業属性や廃止したルールテーブルには依存しない。
    weekday_restrictions: dict[int, TaskWeekdayRestriction] = field(default_factory=dict)
    # 工程追加後など、作業本体がまだ揃っていないオーダーを計算前に通知する。
    errors: list[str] = field(default_factory=list)


# 準備＋固定＋数量×単位当たり時間を、整数分へ切り上げて求める。
def option_duration(setup: int | None, fixed: int | None, processing_minutes: float, quantity: float) -> int:
    # 小数の計算誤差で、ちょうどの分数が余分に切り上がることを防ぐ。
    run = round(float(quantity or 0) * float(processing_minutes or 0), 6)
    # 準備・固定のNULLは保存値を変えず、所要時間の計算時だけ0分にする。
    return int((setup or 0) + (fixed or 0) + math.ceil(run))


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
            Task.OrderID.in_(batch), Task.ProductProcessID.is_not(None),
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
        # DBを直接更新した場合も、曜日・期間の不正値を計算前に拒否する。
        validate_weekday_settings(process, {})
        result.weekday_restrictions[task.TaskID] = TaskWeekdayRestriction(
            weekdays=list(process.AllowedWeekdaysJSON), enabled=process.WeekdayRestrictionEnabled,
            start_at=process.WeekdayRestrictionStartAt, end_at=process.WeekdayRestrictionEndAt,
        )
        # 工程の時間を一度だけ計算し、画面表示とすべての設備候補で共用する。
        timing = TaskTiming(
            duration_min=option_duration(process.SetupMinutes, process.FixedMinutes,
                                         process.ProcessingMinutes, order.Quantity),
            setup_minutes=process.SetupMinutes or 0,
        )
        result.timings[task.TaskID] = timing
        result.options[task.TaskID] = [
            TaskOption(
                option_id=candidate.ProductProcessResourceID,
                resource_id=candidate.ResourceID, resource_group_id=candidate.ResourceGroupID,
                duration_min=timing.duration_min,
                setup_minutes=timing.setup_minutes,
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

"""トランザクションテーブル（T_*）: 需要、計画、ソルバー実行、実績。"""
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.core.db import Base
from app.models.base import AuditMixin, SoftDeleteMixin, in_check
from app.models.types import DateTime, String, Text

# SQLite は INTEGER PRIMARY KEY のみ自動採番するため、BIGINT は SQL Server でのみ使う。
BigId = BigInteger().with_variant(Integer, "sqlite")

# オーダーの種別と状態は、改称前と同じ保存値を使用する。
ORDER_TYPE = ["ORDER", "PROJECT"]
ORDER_STATUSES = ["OPEN", "PLANNED", "IN_PROGRESS", "DONE", "CANCELLED"]
PLAN_OWNERS = ["SCHEDULER", "EXTERNAL"]
TASK_STATUSES = ["NOT_STARTED", "IN_PROGRESS", "DONE", "CANCELLED"]
PLAN_STATUSES = ["DRAFT", "MASTER", "SUPERSEDED", "DISCARDED", "ARCHIVED"]
ASSIGNMENT_SOURCES = ["SOLVER", "MANUAL", "IMPORT"]
RUN_STATUSES = ["QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED"]
RUN_SCOPES = ["FULL", "REPAIR"]
SEVERITIES = ["HARD", "SOFT", "INFO"]
# 作業終了時だけ完了・中断を記録する。作業中はStatusとEndAtをNULLにする。
ACTUAL_STATUSES = ["DONE", "SUSPENDED"]


# ---------------------------------------------------------------- 需要
class Order(AuditMixin, SoftDeleteMixin, Base):
    """オーダー（受注・プロジェクト）。変更後のDB名称を直接使用する。"""

    # 実DBもT_OrdersとOrder系の列名へ変更されることを前提とする。
    __tablename__ = "T_Orders"
    __table_args__ = (
        UniqueConstraint("LocationID", "WBSNumber"),
        CheckConstraint(in_check("OrderType", ORDER_TYPE), name="OrderType"),
        CheckConstraint(in_check("Status", ORDER_STATUSES), name="Status"),
        CheckConstraint(in_check("PlanOwner", PLAN_OWNERS), name="PlanOwner"),
    )
    OrderID = Column(Integer, primary_key=True, autoincrement=True)
    # 拠点の識別番号。既存データのID値と所属関係は維持する。
    LocationID = Column(Integer, ForeignKey("M_Locations.LocationID"), nullable=False)
    # 同じ拠点内でオーダーを区別するWBS番号。
    WBSNumber = Column(String(30), nullable=False)
    OrderName = Column(String(200), nullable=False)
    # 受注かプロジェクトかを表す種別。保存値と動作は維持する。
    OrderType = Column(String(20), nullable=False, default="ORDER")
    # オーダーの対象製品。ProductIDで製品マスタを参照する。
    ProductID = Column(Integer, ForeignKey("M_Product.ProductID"), nullable=True)
    Quantity = Column(Numeric(18, 3), nullable=True)
    CustomerName = Column(String(100), nullable=True)
    ReleaseAt = Column(DateTime, nullable=True)
    # 計算で使う納期と、任意入力の出荷日時。日時は日本時間で保存する。
    DeadLine = Column(DateTime, nullable=True)
    ShippingDate = Column(DateTime, nullable=True)
    Priority = Column(Integer, nullable=False, default=50)  # 1 = 最優先
    Status = Column(String(20), nullable=False, default="OPEN")
    PlanOwner = Column(String(20), nullable=False, default="SCHEDULER")
    AttributesJSON = Column(JSON, nullable=True)
    Remarks = Column(String(500), nullable=True)

    # このオーダーに属するタスク。親子階層を持たず、工程順で取得する。
    tasks = relationship("Task", back_populates="order", order_by="Task.Sequence")


class Task(AuditMixin, Base):
    """オーダーごとの作業。設備候補・前後関係は製品工程から計算時に組み立てる。"""

    __tablename__ = "T_Tasks"
    __table_args__ = (
        UniqueConstraint("OrderID", "TaskNo"),
        CheckConstraint(in_check("Status", TASK_STATUSES), name="Status"),
    )
    # 計画・違反・実績から同じ作業を参照する識別番号。
    TaskID = Column(Integer, primary_key=True, autoincrement=True)
    # タスクの所属先は、変更後のオーダーテーブルを参照する。
    OrderID = Column(Integer, ForeignKey("T_Orders.OrderID"), nullable=False)
    # タスク生成元の製品工程。生成済みのタスクと工程の対応を保持する。
    ProductProcessID = Column(Integer, ForeignKey("M_ProductProcesses.ProductProcessID"), nullable=True)
    # 生成時点の作業番号・名称・並び順。計算上の工程順序は製品マスタを参照する。
    TaskNo = Column(String(30), nullable=False)
    TaskName = Column(String(200), nullable=False)
    Sequence = Column(Integer, nullable=False, default=0)
    # 集約タスクを計算対象から外す区分と、作業固有の開始可能日時・期限。
    IsSummary = Column(Boolean, nullable=False, default=False)
    EarliestStartAt = Column(DateTime, nullable=True)
    DeadlineAt = Column(DateTime, nullable=True)
    # 全計画で共有する作業状態と進捗率。
    Status = Column(String(20), nullable=False, default="NOT_STARTED")
    ProgressPct = Column(Numeric(5, 2), nullable=False, default=0)
    # オーダーから引き継ぐ分類属性。ルールと製品切替時間の判定に使う。
    AttributesJSON = Column(JSON, nullable=True)

    # この作業が所属するオーダー。
    order = relationship("Order", back_populates="tasks")


# ---------------------------------------------------------------- 計画
class Plan(AuditMixin, Base):
    """計画 — 1 つの版: DRAFT / MASTER / SUPERSEDED / DISCARDED / ARCHIVED。"""

    __tablename__ = "T_Plans"
    __table_args__ = (
        # 下書き・マスタ・破棄済みを含め、同じ拠点の計画名の重複を防ぐ。
        UniqueConstraint("LocationID", "PlanName"),
        CheckConstraint(in_check("Status", PLAN_STATUSES), name="Status"),
    )
    PlanID = Column(Integer, primary_key=True, autoincrement=True)
    # 拠点の識別番号。既存データのID値と所属関係は維持する。
    LocationID = Column(Integer, ForeignKey("M_Locations.LocationID"), nullable=False)
    # 画面で計画を識別する名前。同じ拠点内で一意とする。
    PlanName = Column(String(100), nullable=False)
    Status = Column(String(20), nullable=False, default="DRAFT")
    StartAt = Column(DateTime, nullable=False)
    EndAt = Column(DateTime, nullable=False)
    # 計画の計算条件を参照する識別番号。
    CalculationSettingID = Column(Integer, ForeignKey("M_CalculationSettings.CalculationSettingID"), nullable=False)
    BasePlanID = Column(Integer, ForeignKey("T_Plans.PlanID"), nullable=True)
    SupersededAt = Column(DateTime, nullable=True)
    ApprovedAt = Column(DateTime, nullable=True)
    ApprovedBy = Column(String(254), nullable=True)
    # 計画に関する任意の補足情報。
    Remarks = Column(String(500), nullable=True)
    # 楽観的排他制御。SQL Server の rowversion は SQLite に移植できないため、
    # SQLAlchemy が管理する整数のバージョンカウンタを使う。
    RowVer = Column(Integer, nullable=False, default=1)

    __mapper_args__ = {"version_id_col": RowVer}


class PlanAssignment(AuditMixin, Base):
    """計画割付 — 1 つの計画内で、タスクをリソースと時刻に割り付けたもの。"""

    __tablename__ = "T_PlanAssignments"
    __table_args__ = (
        UniqueConstraint("PlanID", "TaskID"),
        CheckConstraint("EndAt > StartAt", name="EndAfterStart"),
        CheckConstraint(in_check("Source", ASSIGNMENT_SOURCES), name="Source"),
        Index("IX_T_PlanAssignments_PlanID_ResourceID_StartAt", "PlanID", "ResourceID", "StartAt"),
    )
    AssignmentID = Column(BigId, primary_key=True, autoincrement=True)
    PlanID = Column(Integer, ForeignKey("T_Plans.PlanID", ondelete="CASCADE"), nullable=False)
    TaskID = Column(Integer, ForeignKey("T_Tasks.TaskID"), nullable=False)
    ResourceID = Column(Integer, ForeignKey("M_Resources.ResourceID"), nullable=False)
    StartAt = Column(DateTime, nullable=False)  # 日本時間。タスク開始時刻（段取りは SetupMinutes として直前に置く）
    EndAt = Column(DateTime, nullable=False)  # 日本時間
    SetupMinutes = Column(Integer, nullable=False, default=0)
    Units = Column(Numeric(5, 2), nullable=False, default=1)
    IsLocked = Column(Boolean, nullable=False, default=False)
    Source = Column(String(10), nullable=False, default="SOLVER")
    RowVer = Column(Integer, nullable=False, default=1)

    __mapper_args__ = {"version_id_col": RowVer}


class SolverRun(AuditMixin, Base):
    """ソルバー実行 — ワーカーがポーリングする作業キューも兼ねる。"""

    # 計算依頼・進捗・結果の保存先。手動で改称したDBテーブルを参照する。
    __tablename__ = "T_SolverRunResult"
    __table_args__ = (
        CheckConstraint(in_check("Status", RUN_STATUSES), name="Status"),
        CheckConstraint(in_check("Scope", RUN_SCOPES), name="Scope"),
        # 待機中の計算依頼を受付順に探す索引。定義名もテーブル名へ揃える。
        Index("IX_T_SolverRunResult_Status_RequestedAt", "Status", "RequestedAt"),
    )
    # 計算実行の識別番号と、その計算を依頼した計画。
    RunID = Column(Integer, primary_key=True, autoincrement=True)
    PlanID = Column(Integer, ForeignKey("T_Plans.PlanID"), nullable=False)
    # 実行状態と、全体計算・部分再計算の区分。
    Status = Column(String(20), nullable=False, default="QUEUED")
    Scope = Column(String(20), nullable=False, default="FULL")
    # 依頼者と、受付・開始・終了の時刻。
    RequestedBy = Column(String(254), nullable=False)
    RequestedAt = Column(DateTime, nullable=False)
    StartAt = Column(DateTime, nullable=True)
    EndAt = Column(DateTime, nullable=True)
    # 時間で打ち切らず、計算エンジンが返す終了状態を保存する。
    SolverStatus = Column(String(20), nullable=True)
    # 得られた計画の評価値と、計算中に求めた評価値の境界。
    ObjectiveValue = Column(Float, nullable=True)
    BestBound = Column(Float, nullable=True)
    # 計算対象のタスク数、進捗の詳細、失敗時の理由。
    TaskCount = Column(Integer, nullable=True)
    ProgressJSON = Column(JSON, nullable=True)
    ErrorMessage = Column(Text, nullable=True)


class PlanKpi(Base):
    """計画KPI"""

    __tablename__ = "T_PlanKpis"
    PlanID = Column(Integer, ForeignKey("T_Plans.PlanID", ondelete="CASCADE"), primary_key=True)
    # 集計名はlate_orders等のプログラム上の名称をそのまま保存する。
    KpiKey = Column(String(50), primary_key=True)
    KpiValue = Column(Numeric(18, 4), nullable=False)


class PlanViolation(AuditMixin, Base):
    """制約違反"""

    __tablename__ = "T_PlanViolations"
    __table_args__ = (CheckConstraint(in_check("Severity", SEVERITIES), name="Severity"),)
    ViolationID = Column(BigId, primary_key=True, autoincrement=True)
    PlanID = Column(Integer, ForeignKey("T_Plans.PlanID", ondelete="CASCADE"), nullable=False)
    RuleID = Column(Integer, ForeignKey("M_Rules.RuleID"), nullable=True)
    TaskID = Column(Integer, ForeignKey("T_Tasks.TaskID"), nullable=True)
    Severity = Column(String(10), nullable=False)
    # 違反は重大度・対象タスク・ルール・説明で保持する。
    Penalty = Column(Numeric(18, 2), nullable=True)
    Message = Column(String(500), nullable=False)


# ---------------------------------------------------------------- 実行
class WorkActual(AuditMixin, Base):
    """作業実績。タスクの開始・終了日時、完了・中断、数量を保持する。"""

    __tablename__ = "T_WorkActuals"
    __table_args__ = (
        CheckConstraint(in_check("Status", ACTUAL_STATUSES), name="Status"),
        # 作業中は両方NULL、終了後は日時と完了・中断を必ず組にする。
        CheckConstraint(
            "(EndAt IS NULL AND Status IS NULL) OR "
            "(EndAt IS NOT NULL AND Status IS NOT NULL)", name="EndStatus",
        ),
        CheckConstraint("EndAt IS NULL OR (StartAt IS NOT NULL AND EndAt >= StartAt)", name="EndAfterStart"),
    )
    # 作業実績を識別する自動採番の番号。
    WorkActualID = Column(BigId, primary_key=True, autoincrement=True)
    TaskID = Column(Integer, ForeignKey("T_Tasks.TaskID"), nullable=False)
    ResourceID = Column(Integer, ForeignKey("M_Resources.ResourceID"), nullable=True)
    # 開始・終了は日本時間。作業日と工数はこの日時から求める。
    StartAt = Column(DateTime, nullable=True)
    EndAt = Column(DateTime, nullable=True)
    # 実際に完了した数量。画面からの実績CRUDは追加しない。
    Quantity = Column(Numeric(18, 3), nullable=True)
    # NULLは作業中、DONEは完了、SUSPENDEDは中断。
    Status = Column(String(20), nullable=True)
    Remarks = Column(String(500), nullable=True)

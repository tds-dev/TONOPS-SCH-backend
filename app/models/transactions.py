"""トランザクションテーブル（T_*）: 需要、計画、ソルバー実行、実績。"""
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Date,
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
DEP_TYPES = ["FS", "SS", "FF", "SF"]
PLAN_STATUSES = ["DRAFT", "MASTER", "SUPERSEDED", "DISCARDED", "ARCHIVED"]
ASSIGNMENT_SOURCES = ["SOLVER", "MANUAL", "IMPORT"]
RUN_STATUSES = ["QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED"]
RUN_SCOPES = ["FULL", "REPAIR"]
SEVERITIES = ["HARD", "SOFT", "INFO"]
ACTUAL_STATUSES = ["IN_PROGRESS", "DONE", "SUSPENDED"]
ACTUAL_SOURCES = ["MANUAL", "PMS", "IMPORT"]


# ---------------------------------------------------------------- 需要
class Order(AuditMixin, SoftDeleteMixin, Base):
    """オーダー（受注・プロジェクト）。変更後のDB名称を直接使用する。"""

    # 実DBもT_OrdersとOrder系の列名へ変更されることを前提とする。
    __tablename__ = "T_Orders"
    __table_args__ = (
        UniqueConstraint("LocationID", "OrderNo"),
        CheckConstraint(in_check("OrderType", ORDER_TYPE), name="OrderType"),
        CheckConstraint(in_check("Status", ORDER_STATUSES), name="Status"),
        CheckConstraint(in_check("PlanOwner", PLAN_OWNERS), name="PlanOwner"),
    )
    OrderID = Column(Integer, primary_key=True, autoincrement=True)
    # 拠点の識別番号。既存データのID値と所属関係は維持する。
    LocationID = Column(Integer, ForeignKey("M_Locations.LocationID"), nullable=False)
    OrderNo = Column(String(30), nullable=False)
    OrderName = Column(String(200), nullable=False)
    # 受注かプロジェクトかを表す種別。保存値と動作は維持する。
    OrderType = Column(String(20), nullable=False, default="ORDER")
    ParentOrderID = Column(Integer, ForeignKey("T_Orders.OrderID"), nullable=True)
    ItemID = Column(Integer, ForeignKey("M_Items.ItemID"), nullable=True)
    RoutingID = Column(Integer, ForeignKey("M_Routings.RoutingID"), nullable=True)
    Quantity = Column(Numeric(18, 3), nullable=True)
    CustomerName = Column(String(100), nullable=True)
    ReleaseAt = Column(DateTime, nullable=True)
    DueAt = Column(DateTime, nullable=True)
    Priority = Column(Integer, nullable=False, default=50)  # 1 = 最優先
    Status = Column(String(20), nullable=False, default="OPEN")
    PlanOwner = Column(String(20), nullable=False, default="SCHEDULER")
    AttributesJSON = Column(JSON, nullable=True)
    Remarks = Column(String(500), nullable=True)

    tasks = relationship("Task", back_populates="order", order_by="Task.Sequence")


class Task(AuditMixin, Base):
    """タスク — エンジンがスケジュールする単位（IsSummary の場合を除く）。"""

    __tablename__ = "T_Tasks"
    __table_args__ = (
        UniqueConstraint("OrderID", "TaskNo"),
        CheckConstraint(in_check("Status", TASK_STATUSES), name="Status"),
    )
    TaskID = Column(Integer, primary_key=True, autoincrement=True)
    # 作業の所属先は、変更後のオーダーテーブルを参照する。
    OrderID = Column(Integer, ForeignKey("T_Orders.OrderID"), nullable=False)
    ParentTaskID = Column(Integer, ForeignKey("T_Tasks.TaskID"), nullable=True)
    RoutingStepID = Column(Integer, ForeignKey("M_RoutingSteps.RoutingStepID"), nullable=True)
    TaskNo = Column(String(30), nullable=False)
    TaskName = Column(String(200), nullable=False)
    Sequence = Column(Integer, nullable=False, default=0)
    IsSummary = Column(Boolean, nullable=False, default=False)
    IsMilestone = Column(Boolean, nullable=False, default=False)
    EffortHours = Column(Numeric(9, 2), nullable=True)
    EarliestStartAt = Column(DateTime, nullable=True)
    DeadlineAt = Column(DateTime, nullable=True)
    Status = Column(String(20), nullable=False, default="NOT_STARTED")
    ProgressPct = Column(Numeric(5, 2), nullable=False, default=0)
    AttributesJSON = Column(JSON, nullable=True)

    order = relationship("Order", back_populates="tasks")
    options = relationship(
        "TaskResourceOption", cascade="all, delete-orphan", lazy="selectin"
    )


class TaskResourceOption(AuditMixin, Base):
    """タスクリソース候補"""

    __tablename__ = "T_TaskResourceOptions"
    __table_args__ = (
        CheckConstraint(
            "(ResourceID IS NULL AND ResourceGroupID IS NOT NULL) OR "
            "(ResourceID IS NOT NULL AND ResourceGroupID IS NULL)",
            name="ResourceOrGroup",
        ),
    )
    OptionID = Column(Integer, primary_key=True, autoincrement=True)
    TaskID = Column(Integer, ForeignKey("T_Tasks.TaskID", ondelete="CASCADE"), nullable=False)
    ResourceID = Column(Integer, ForeignKey("M_Resources.ResourceID"), nullable=True)
    ResourceGroupID = Column(Integer, ForeignKey("M_ResourceGroups.ResourceGroupID"), nullable=True)
    DurationMin = Column(Integer, nullable=False)
    SetupMinutes = Column(Integer, nullable=False, default=0)
    Units = Column(Numeric(5, 2), nullable=False, default=1)
    Priority = Column(Integer, nullable=False, default=1)


class TaskDependency(AuditMixin, Base):
    """タスク依存関係"""

    __tablename__ = "T_TaskDependencies"
    __table_args__ = (
        UniqueConstraint("PredecessorTaskID", "SuccessorTaskID"),
        CheckConstraint(in_check("DependencyType", DEP_TYPES), name="DependencyType"),
    )
    DependencyID = Column(Integer, primary_key=True, autoincrement=True)
    PredecessorTaskID = Column(Integer, ForeignKey("T_Tasks.TaskID"), nullable=False)
    SuccessorTaskID = Column(Integer, ForeignKey("T_Tasks.TaskID"), nullable=False)
    DependencyType = Column(String(2), nullable=False, default="FS")
    LagMin = Column(Integer, nullable=False, default=0)
    MaxLagMin = Column(Integer, nullable=True)


# ---------------------------------------------------------------- 計画
class Plan(AuditMixin, Base):
    """計画 — 1 つの版: DRAFT / MASTER / SUPERSEDED / DISCARDED / ARCHIVED。"""

    __tablename__ = "T_Plans"
    __table_args__ = (
        UniqueConstraint("LocationID", "PlanNo"),
        CheckConstraint(in_check("Status", PLAN_STATUSES), name="Status"),
    )
    PlanID = Column(Integer, primary_key=True, autoincrement=True)
    # 拠点の識別番号。既存データのID値と所属関係は維持する。
    LocationID = Column(Integer, ForeignKey("M_Locations.LocationID"), nullable=False)
    PlanNo = Column(String(30), nullable=False)
    PlanName = Column(String(100), nullable=False)
    Status = Column(String(20), nullable=False, default="DRAFT")
    HorizonStart = Column(DateTime, nullable=False)
    HorizonEnd = Column(DateTime, nullable=False)
    ProfileID = Column(Integer, ForeignKey("M_PlanProfiles.ProfileID"), nullable=False)
    BasePlanID = Column(Integer, ForeignKey("T_Plans.PlanID"), nullable=True)
    SupersededAt = Column(DateTime, nullable=True)
    ApprovedAt = Column(DateTime, nullable=True)
    ApprovedBy = Column(String(254), nullable=True)
    Memo = Column(String(500), nullable=True)
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
    StartAt = Column(DateTime, nullable=False)  # UTC。作業開始時刻（段取りは SetupMinutes として直前に置く）
    EndAt = Column(DateTime, nullable=False)  # UTC
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
    StartedAt = Column(DateTime, nullable=True)
    FinishedAt = Column(DateTime, nullable=True)
    # 計算の制限秒数と、計算エンジンが返す終了状態。
    TimeLimitSec = Column(Integer, nullable=False, default=60)
    SolverStatus = Column(String(20), nullable=True)
    # 得られた計画の評価値と、計算中に求めた評価値の境界。
    ObjectiveValue = Column(Float, nullable=True)
    BestBound = Column(Float, nullable=True)
    # 計算対象の作業数、進捗の詳細、失敗時の理由。
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
    # 違反コードはLATE_ORDER等のプログラム上の名称をそのまま保存する。
    ViolationCode = Column(String(30), nullable=False, default="OTHER")
    Penalty = Column(Numeric(18, 2), nullable=True)
    Message = Column(String(500), nullable=False)


# ---------------------------------------------------------------- 実行
class Actual(AuditMixin, Base):
    """実績"""

    __tablename__ = "T_Actuals"
    __table_args__ = (
        CheckConstraint(in_check("Status", ACTUAL_STATUSES), name="Status"),
        CheckConstraint(in_check("Source", ACTUAL_SOURCES), name="Source"),
    )
    ActualID = Column(BigId, primary_key=True, autoincrement=True)
    TaskID = Column(Integer, ForeignKey("T_Tasks.TaskID"), nullable=False)
    ResourceID = Column(Integer, ForeignKey("M_Resources.ResourceID"), nullable=True)
    StartAt = Column(DateTime, nullable=True)
    EndAt = Column(DateTime, nullable=True)
    WorkDate = Column(Date, nullable=True)
    WorkHours = Column(Numeric(9, 2), nullable=True)
    Quantity = Column(Numeric(18, 3), nullable=True)
    Status = Column(String(20), nullable=False, default="DONE")
    Source = Column(String(10), nullable=False, default="MANUAL")
    ExternalKey = Column(String(100), nullable=True)
    Remarks = Column(String(500), nullable=True)

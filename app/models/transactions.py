"""Transaction tables (T_*): demand, plans, solver runs, actuals."""
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.core.db import Base
from app.models.base import AuditMixin, SoftDeleteMixin, in_check

# SQLite only auto-increments INTEGER PRIMARY KEY; use BIGINT on SQL Server only.
BigId = BigInteger().with_variant(Integer, "sqlite")

JOB_KINDS = ["ORDER", "PROJECT"]
JOB_STATUSES = ["OPEN", "PLANNED", "IN_PROGRESS", "DONE", "CANCELLED"]
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


# ---------------------------------------------------------------- demand
class Job(AuditMixin, SoftDeleteMixin, Base):
    """ジョブ（オーダー・プロジェクト）"""

    __tablename__ = "T_Jobs"
    __table_args__ = (
        UniqueConstraint("SiteID", "JobNo"),
        CheckConstraint(in_check("JobKind", JOB_KINDS), name="JobKind"),
        CheckConstraint(in_check("Status", JOB_STATUSES), name="Status"),
        CheckConstraint(in_check("PlanOwner", PLAN_OWNERS), name="PlanOwner"),
    )
    JobID = Column(Integer, primary_key=True, autoincrement=True)
    SiteID = Column(Integer, ForeignKey("M_Sites.SiteID"), nullable=False)
    JobNo = Column(String(30), nullable=False)
    JobName = Column(String(200), nullable=False)
    JobKind = Column(String(20), nullable=False, default="ORDER")
    ParentJobID = Column(Integer, ForeignKey("T_Jobs.JobID"), nullable=True)
    ItemID = Column(Integer, ForeignKey("M_Items.ItemID"), nullable=True)
    RoutingID = Column(Integer, ForeignKey("M_Routings.RoutingID"), nullable=True)
    Quantity = Column(Numeric(18, 3), nullable=True)
    CustomerName = Column(String(100), nullable=True)
    ReleaseAt = Column(DateTime, nullable=True)
    DueAt = Column(DateTime, nullable=True)
    Priority = Column(Integer, nullable=False, default=50)  # 1 = highest
    Status = Column(String(20), nullable=False, default="OPEN")
    PlanOwner = Column(String(20), nullable=False, default="SCHEDULER")
    AttributesJSON = Column(JSON, nullable=True)
    Remarks = Column(String(500), nullable=True)

    tasks = relationship("Task", back_populates="job", order_by="Task.Sequence")


class Task(AuditMixin, Base):
    """タスク — the unit the engine schedules (unless IsSummary)."""

    __tablename__ = "T_Tasks"
    __table_args__ = (
        UniqueConstraint("JobID", "TaskNo"),
        CheckConstraint(in_check("Status", TASK_STATUSES), name="Status"),
    )
    TaskID = Column(Integer, primary_key=True, autoincrement=True)
    JobID = Column(Integer, ForeignKey("T_Jobs.JobID"), nullable=False)
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

    job = relationship("Job", back_populates="tasks")
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


# ---------------------------------------------------------------- planning
class Plan(AuditMixin, Base):
    """計画 — one version: DRAFT / MASTER / SUPERSEDED / DISCARDED / ARCHIVED."""

    __tablename__ = "T_Plans"
    __table_args__ = (
        UniqueConstraint("SiteID", "PlanNo"),
        CheckConstraint(in_check("Status", PLAN_STATUSES), name="Status"),
    )
    PlanID = Column(Integer, primary_key=True, autoincrement=True)
    SiteID = Column(Integer, ForeignKey("M_Sites.SiteID"), nullable=False)
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
    # Optimistic concurrency. SQL Server's rowversion is not portable to SQLite,
    # so we use an integer version counter managed by SQLAlchemy.
    RowVer = Column(Integer, nullable=False, default=1)

    __mapper_args__ = {"version_id_col": RowVer}


class PlanAssignment(AuditMixin, Base):
    """計画割付 — a task on a resource at a time, within one plan."""

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
    StartAt = Column(DateTime, nullable=False)  # UTC, includes setup
    EndAt = Column(DateTime, nullable=False)  # UTC
    SetupMinutes = Column(Integer, nullable=False, default=0)
    Units = Column(Numeric(5, 2), nullable=False, default=1)
    IsLocked = Column(Boolean, nullable=False, default=False)
    Source = Column(String(10), nullable=False, default="SOLVER")
    RowVer = Column(Integer, nullable=False, default=1)

    __mapper_args__ = {"version_id_col": RowVer}


class SolverRun(AuditMixin, Base):
    """ソルバー実行 — also the work queue polled by the worker."""

    __tablename__ = "T_SolverRuns"
    __table_args__ = (
        CheckConstraint(in_check("Status", RUN_STATUSES), name="Status"),
        CheckConstraint(in_check("Scope", RUN_SCOPES), name="Scope"),
        Index("IX_T_SolverRuns_Status_RequestedAt", "Status", "RequestedAt"),
    )
    RunID = Column(Integer, primary_key=True, autoincrement=True)
    PlanID = Column(Integer, ForeignKey("T_Plans.PlanID"), nullable=False)
    Status = Column(String(20), nullable=False, default="QUEUED")
    Scope = Column(String(20), nullable=False, default="FULL")
    RequestedBy = Column(String(254), nullable=False)
    RequestedAt = Column(DateTime, nullable=False)
    StartedAt = Column(DateTime, nullable=True)
    FinishedAt = Column(DateTime, nullable=True)
    TimeLimitSec = Column(Integer, nullable=False, default=60)
    SolverStatus = Column(String(20), nullable=True)
    ObjectiveValue = Column(Float, nullable=True)
    BestBound = Column(Float, nullable=True)
    TaskCount = Column(Integer, nullable=True)
    ProgressJSON = Column(JSON, nullable=True)
    ErrorMessage = Column(Text, nullable=True)


class PlanKpi(Base):
    """計画KPI"""

    __tablename__ = "T_PlanKpis"
    PlanID = Column(Integer, ForeignKey("T_Plans.PlanID", ondelete="CASCADE"), primary_key=True)
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
    Penalty = Column(Numeric(18, 2), nullable=True)
    Message = Column(String(500), nullable=False)


# ---------------------------------------------------------------- execution
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

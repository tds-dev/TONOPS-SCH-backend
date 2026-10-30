"""マスタテーブル（M_*）。列名は設計書に合わせて PascalCase。"""
from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.core.db import Base
from app.models.base import AuditMixin, SoftDeleteMixin, in_check
from app.models.types import DateTime, String

# リソース種別の許可値。名称のみをTYPEへ統一し、保存値は維持する。
RESOURCE_TYPE = ["MACHINE", "PERSON", "TEAM", "ROOM", "OTHER"]
# 属性の対象区分は、プログラムと変更後のDBで同じ名称を使用する。
ENTITY_TYPES = ["ITEM", "RESOURCE", "ORDER", "TASK"]
DATA_TYPES = ["TEXT", "NUMBER", "BOOL", "DATE", "ENUM"]
TIME_UNITS = ["MINUTE", "DAY"]


# ---------------------------------------------------------------- テナント
class Organization(AuditMixin, SoftDeleteMixin, Base):
    """組織マスタ"""

    __tablename__ = "M_Organizations"
    OrganizationID = Column(Integer, primary_key=True, autoincrement=True)
    OrganizationCode = Column(String(30), nullable=False, unique=True)
    OrganizationName = Column(String(100), nullable=False)


class Location(AuditMixin, SoftDeleteMixin, Base):
    """拠点マスタ"""

    __tablename__ = "M_Locations"
    __table_args__ = (UniqueConstraint("OrganizationID", "LocationCode"),)
    # 拠点の識別番号。既存データのID値と所属関係は維持する。
    LocationID = Column(Integer, primary_key=True, autoincrement=True)
    OrganizationID = Column(Integer, ForeignKey("M_Organizations.OrganizationID"), nullable=False)
    # 組織内で拠点を区別するコード。
    LocationCode = Column(String(30), nullable=False)
    # 画面の拠点選択欄に表示する名称。
    LocationName = Column(String(100), nullable=False)
    TimeZone = Column(String(50), nullable=False, default="Asia/Tokyo")
    DefaultCalendarID = Column(
        Integer, ForeignKey("M_Calendars.CalendarID", use_alter=True), nullable=True
    )


# ---------------------------------------------------------------- カレンダー
class Calendar(AuditMixin, SoftDeleteMixin, Base):
    """カレンダーマスタ"""

    __tablename__ = "M_Calendars"
    __table_args__ = (UniqueConstraint("LocationID", "CalendarCode"),)
    CalendarID = Column(Integer, primary_key=True, autoincrement=True)
    # 拠点の識別番号。既存データのID値と所属関係は維持する。
    LocationID = Column(Integer, ForeignKey("M_Locations.LocationID"), nullable=False)
    CalendarCode = Column(String(30), nullable=False)
    CalendarName = Column(String(100), nullable=False)
    ParentCalendarID = Column(Integer, ForeignKey("M_Calendars.CalendarID"), nullable=True)

    patterns = relationship("CalendarPattern", cascade="all, delete-orphan", lazy="selectin")
    exceptions = relationship("CalendarException", cascade="all, delete-orphan", lazy="selectin")
    parent = relationship("Calendar", remote_side=[CalendarID])


class CalendarPattern(AuditMixin, Base):
    """稼働パターンマスタ — 拠点の現地時間による週次シフト。"""

    __tablename__ = "M_CalendarPatterns"
    __table_args__ = (CheckConstraint("DayOfWeek BETWEEN 1 AND 7", name="DayOfWeek"),)
    PatternID = Column(Integer, primary_key=True, autoincrement=True)
    CalendarID = Column(
        Integer, ForeignKey("M_Calendars.CalendarID", ondelete="CASCADE"), nullable=False
    )
    DayOfWeek = Column(SmallInteger, nullable=False)  # 1 = 月 … 7 = 日
    StartTime = Column(Time, nullable=False)
    EndTime = Column(Time, nullable=False)  # StartTime 以下は「日をまたぐ」の意味
    ShiftName = Column(String(50), nullable=True)
    ValidFrom = Column(Date, nullable=True)
    ValidTo = Column(Date, nullable=True)


class CalendarException(AuditMixin, Base):
    """稼働例外マスタ — 休日・停止（IsWorking=0）または残業（IsWorking=1）。"""

    __tablename__ = "M_CalendarExceptions"
    ExceptionID = Column(Integer, primary_key=True, autoincrement=True)
    CalendarID = Column(
        Integer, ForeignKey("M_Calendars.CalendarID", ondelete="CASCADE"), nullable=False
    )
    StartAt = Column(DateTime, nullable=False)  # UTC
    EndAt = Column(DateTime, nullable=False)  # UTC
    IsWorking = Column(Boolean, nullable=False, default=False)
    Reason = Column(String(100), nullable=True)


# ---------------------------------------------------------------- リソース
class ResourceGroup(AuditMixin, SoftDeleteMixin, Base):
    """リソースグループマスタ"""

    __tablename__ = "M_ResourceGroups"
    __table_args__ = (UniqueConstraint("LocationID", "GroupCode"),)
    ResourceGroupID = Column(Integer, primary_key=True, autoincrement=True)
    # 拠点の識別番号。既存データのID値と所属関係は維持する。
    LocationID = Column(Integer, ForeignKey("M_Locations.LocationID"), nullable=False)
    GroupCode = Column(String(30), nullable=False)
    GroupName = Column(String(100), nullable=False)
    SortOrder = Column(Integer, nullable=False, default=0)


class Resource(AuditMixin, SoftDeleteMixin, Base):
    """リソースマスタ"""

    __tablename__ = "M_Resources"
    __table_args__ = (
        UniqueConstraint("LocationID", "ResourceCode"),
        CheckConstraint(in_check("ResourceType", RESOURCE_TYPE), name="ResourceType"),
    )
    ResourceID = Column(Integer, primary_key=True, autoincrement=True)
    # 拠点の識別番号。既存データのID値と所属関係は維持する。
    LocationID = Column(Integer, ForeignKey("M_Locations.LocationID"), nullable=False)
    ResourceGroupID = Column(Integer, ForeignKey("M_ResourceGroups.ResourceGroupID"), nullable=True)
    ResourceCode = Column(String(30), nullable=False)
    ResourceName = Column(String(100), nullable=False)
    # リソースの種別を、APIとDBで共通のType名として扱う。
    ResourceType = Column(String(20), nullable=False, default="MACHINE")
    Capacity = Column(Numeric(9, 2), nullable=False, default=1)
    DailyCapacityHours = Column(Numeric(5, 2), nullable=True)
    CalendarID = Column(Integer, ForeignKey("M_Calendars.CalendarID"), nullable=True)
    CostPerHour = Column(Numeric(12, 2), nullable=True)
    AttributesJSON = Column(JSON, nullable=True)
    SortOrder = Column(Integer, nullable=False, default=0)


# ---------------------------------------------------------------- 設定
class AttributeDefinition(AuditMixin, Base):
    """属性定義マスタ"""

    __tablename__ = "M_AttributeDefinitions"
    __table_args__ = (
        UniqueConstraint("OrganizationID", "EntityType", "AttributeKey"),
        CheckConstraint(in_check("EntityType", ENTITY_TYPES), name="EntityType"),
        CheckConstraint(in_check("DataType", DATA_TYPES), name="DataType"),
    )
    AttributeDefID = Column(Integer, primary_key=True, autoincrement=True)
    OrganizationID = Column(Integer, ForeignKey("M_Organizations.OrganizationID"), nullable=False)
    # オーダーの属性はORDER区分として保存・検索する。
    EntityType = Column(String(20), nullable=False)
    AttributeKey = Column(String(50), nullable=False)
    Label = Column(String(100), nullable=False)
    DataType = Column(String(20), nullable=False, default="TEXT")
    EnumValuesJSON = Column(JSON, nullable=True)
    IsRequired = Column(Boolean, nullable=False, default=False)
    SortOrder = Column(Integer, nullable=False, default=0)


class Rule(AuditMixin, Base):
    """制約ルールマスタ — ルールプラグインの 1 インスタンス。対象はセレクターで絞り込む。"""

    __tablename__ = "M_Rules"
    RuleID = Column(Integer, primary_key=True, autoincrement=True)
    # 拠点の識別番号。既存データのID値と所属関係は維持する。
    LocationID = Column(Integer, ForeignKey("M_Locations.LocationID"), nullable=False)
    RuleTypeKey = Column(String(50), nullable=False)
    RuleName = Column(String(100), nullable=False)
    SelectorJSON = Column(JSON, nullable=False, default=dict)
    ParamsJSON = Column(JSON, nullable=False, default=dict)
    IsHard = Column(Boolean, nullable=False, default=True)
    Weight = Column(Integer, nullable=False, default=100)
    ValidFrom = Column(Date, nullable=True)
    ValidTo = Column(Date, nullable=True)
    IsActive = Column(Boolean, nullable=False, default=True)


class ChangeoverMatrix(AuditMixin, Base):
    """段取り替えマトリクスマスタ"""

    __tablename__ = "M_ChangeoverMatrices"
    MatrixID = Column(Integer, primary_key=True, autoincrement=True)
    # 拠点の識別番号。既存データのID値と所属関係は維持する。
    LocationID = Column(Integer, ForeignKey("M_Locations.LocationID"), nullable=False)
    MatrixName = Column(String(100), nullable=False)
    AttributeKey = Column(String(50), nullable=False)
    ResourceGroupID = Column(Integer, ForeignKey("M_ResourceGroups.ResourceGroupID"), nullable=True)
    DefaultMinutes = Column(Integer, nullable=False, default=0)
    IsActive = Column(Boolean, nullable=False, default=True)

    entries = relationship("ChangeoverEntry", cascade="all, delete-orphan", lazy="selectin")


class ChangeoverEntry(AuditMixin, Base):
    """段取り替え明細マスタ — FromValue/ToValue の '*' は任意の値。"""

    __tablename__ = "M_ChangeoverEntries"
    __table_args__ = (UniqueConstraint("MatrixID", "FromValue", "ToValue"),)
    EntryID = Column(Integer, primary_key=True, autoincrement=True)
    MatrixID = Column(
        Integer, ForeignKey("M_ChangeoverMatrices.MatrixID", ondelete="CASCADE"), nullable=False
    )
    FromValue = Column(String(50), nullable=False)
    ToValue = Column(String(50), nullable=False)
    SetupMinutes = Column(Integer, nullable=False, default=0)
    IsForbidden = Column(Boolean, nullable=False, default=False)
    Cost = Column(Numeric(12, 2), nullable=True)


class PlanProfile(AuditMixin, Base):
    """計画プロファイルマスタ — 目的関数の重みとソルバーの上限。"""

    __tablename__ = "M_PlanProfiles"
    __table_args__ = (CheckConstraint(in_check("TimeUnit", TIME_UNITS), name="TimeUnit"),)
    ProfileID = Column(Integer, primary_key=True, autoincrement=True)
    # 拠点の識別番号。既存データのID値と所属関係は維持する。
    LocationID = Column(Integer, ForeignKey("M_Locations.LocationID"), nullable=False)
    ProfileName = Column(String(100), nullable=False)
    TimeUnit = Column(String(10), nullable=False, default="MINUTE")
    ObjectiveWeightsJSON = Column(JSON, nullable=False, default=dict)
    TimeLimitSec = Column(Integer, nullable=False, default=60)
    FrozenWindowHours = Column(Integer, nullable=False, default=0)
    IsDefault = Column(Boolean, nullable=False, default=False)


# ---------------------------------------------------------------- テンプレート
class Item(AuditMixin, SoftDeleteMixin, Base):
    """品目マスタ"""

    __tablename__ = "M_Items"
    __table_args__ = (UniqueConstraint("LocationID", "ItemCode"),)
    ItemID = Column(Integer, primary_key=True, autoincrement=True)
    # 拠点の識別番号。既存データのID値と所属関係は維持する。
    LocationID = Column(Integer, ForeignKey("M_Locations.LocationID"), nullable=False)
    ItemCode = Column(String(30), nullable=False)
    ItemName = Column(String(100), nullable=False)
    Unit = Column(String(10), nullable=True)
    AttributesJSON = Column(JSON, nullable=True)


class Routing(AuditMixin, SoftDeleteMixin, Base):
    """工程ルートマスタ"""

    __tablename__ = "M_Routings"
    __table_args__ = (UniqueConstraint("ItemID", "Revision"),)
    RoutingID = Column(Integer, primary_key=True, autoincrement=True)
    ItemID = Column(Integer, ForeignKey("M_Items.ItemID"), nullable=False)
    RoutingName = Column(String(100), nullable=False)
    Revision = Column(Integer, nullable=False, default=1)
    IsDefault = Column(Boolean, nullable=False, default=True)

    steps = relationship(
        "RoutingStep", cascade="all, delete-orphan", order_by="RoutingStep.StepNo", lazy="selectin"
    )


class RoutingStep(AuditMixin, Base):
    """工程ルート明細マスタ"""

    __tablename__ = "M_RoutingSteps"
    __table_args__ = (UniqueConstraint("RoutingID", "StepNo"),)
    RoutingStepID = Column(Integer, primary_key=True, autoincrement=True)
    RoutingID = Column(
        Integer, ForeignKey("M_Routings.RoutingID", ondelete="CASCADE"), nullable=False
    )
    StepNo = Column(Integer, nullable=False)
    StepName = Column(String(100), nullable=False)
    MinLagAfterMin = Column(Integer, nullable=False, default=0)
    MaxLagAfterMin = Column(Integer, nullable=True)
    AttributesJSON = Column(JSON, nullable=True)

    resources = relationship(
        "RoutingStepResource", cascade="all, delete-orphan", lazy="selectin"
    )


class RoutingStepResource(AuditMixin, Base):
    """工程リソース候補マスタ — 工程を実行できるリソースまたはグループ。"""

    __tablename__ = "M_RoutingStepResources"
    __table_args__ = (
        CheckConstraint(
            "(ResourceID IS NULL AND ResourceGroupID IS NOT NULL) OR "
            "(ResourceID IS NOT NULL AND ResourceGroupID IS NULL)",
            name="ResourceOrGroup",
        ),
    )
    RoutingStepResourceID = Column(Integer, primary_key=True, autoincrement=True)
    RoutingStepID = Column(
        Integer, ForeignKey("M_RoutingSteps.RoutingStepID", ondelete="CASCADE"), nullable=False
    )
    ResourceID = Column(Integer, ForeignKey("M_Resources.ResourceID"), nullable=True)
    ResourceGroupID = Column(Integer, ForeignKey("M_ResourceGroups.ResourceGroupID"), nullable=True)
    SetupMinutes = Column(Integer, nullable=False, default=0)
    FixedMinutes = Column(Integer, nullable=False, default=0)
    MinutesPerUnit = Column(Numeric(12, 4), nullable=False, default=0)
    Priority = Column(Integer, nullable=False, default=1)

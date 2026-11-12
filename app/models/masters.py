"""マスタテーブル（M_*）。列名は設計書に合わせて PascalCase。"""
from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    ForeignKey,
    ForeignKeyConstraint,
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

# 属性定義の区分。製品の属性欄は廃止済みで、PRODUCTは既存の定義値として保持する。
ENTITY_TYPES = ["PRODUCT", "RESOURCE", "ORDER", "TASK"]
DATA_TYPES = ["TEXT", "NUMBER", "BOOL", "DATE", "ENUM"]
TIME_UNITS = ["MINUTE", "DAY"]


# ---------------------------------------------------------------- 拠点
class Location(AuditMixin, SoftDeleteMixin, Base):
    """拠点マスタ"""

    __tablename__ = "M_Locations"
    # 代表勤務行が必ず同じ拠点に属するよう、拠点番号も組み合わせて参照する。
    __table_args__ = (
        ForeignKeyConstraint(
            ["CalendarID", "LocationID"], ["M_Calendars.CalendarID", "M_Calendars.LocationID"],
            name="FK_M_Locations_CalendarID_M_Calendars", use_alter=True,
        ),
    )
    # 拠点の識別番号。既存データのID値と所属関係は維持する。
    LocationID = Column(Integer, primary_key=True, autoincrement=True)
    # 画面の拠点選択欄に表示する名称。
    LocationName = Column(String(100), nullable=False)
    # 拠点共通カレンダーの代表勤務行。計算には同じ拠点の全勤務行を使う。
    CalendarID = Column(Integer, nullable=True)


# ---------------------------------------------------------------- カレンダー
class Calendar(AuditMixin, SoftDeleteMixin, Base):
    """拠点ごとの週次勤務。1行が1曜日・1時間帯を表す。"""

    __tablename__ = "M_Calendars"
    # 曜日と同日勤務の範囲、拠点の代表勤務行を参照する組合せを定義する。
    __table_args__ = (
        CheckConstraint("DayOfWeek BETWEEN 0 AND 6", name="DayOfWeek"),
        CheckConstraint("EndTime > StartTime", name="EndAfterStart"),
        UniqueConstraint("CalendarID", "LocationID"),
    )
    # 勤務行を識別する番号。カレンダー全体はLocationIDでまとめる。
    CalendarID = Column(Integer, primary_key=True, autoincrement=True)
    # 拠点の識別番号。既存データのID値と所属関係は維持する。
    LocationID = Column(Integer, ForeignKey("M_Locations.LocationID"), nullable=False)
    # 曜日と日本時間の勤務帯。開始から終了までを同じ日付内に収める。
    DayOfWeek = Column(SmallInteger, nullable=False)  # 0 = 日 … 6 = 土
    StartTime = Column(Time, nullable=False)
    EndTime = Column(Time, nullable=False)  # 同じ日のStartTimeより後の時刻。
    # 午前・午後などの勤務名。
    WorkName = Column(String(50), nullable=True)


class CalendarException(AuditMixin, Base):
    """拠点共通の休日・停止時間。週次勤務から指定日時を差し引く。"""

    __tablename__ = "M_CalendarExceptions"
    # 終了が開始より後の停止時間のみ登録する。
    __table_args__ = (CheckConstraint("EndAt > StartAt", name="EndAfterStart"),)
    # 例外の識別番号と、その拠点の代表勤務行。
    ExceptionID = Column(Integer, primary_key=True, autoincrement=True)
    CalendarID = Column(
        Integer, ForeignKey("M_Calendars.CalendarID", ondelete="CASCADE"), nullable=False
    )
    # 時刻だけでなく日付も持つ日本時間の日時。API入出力では時差を変換する。
    StartAt = Column(DateTime, nullable=False)
    EndAt = Column(DateTime, nullable=False)
    # 休日・設備点検などの登録理由。
    Reason = Column(String(100), nullable=True)


# ---------------------------------------------------------------- リソース
class ResourceGroup(AuditMixin, SoftDeleteMixin, Base):
    """リソースグループマスタ"""

    __tablename__ = "M_ResourceGroups"
    ResourceGroupID = Column(Integer, primary_key=True, autoincrement=True)
    # 拠点の識別番号。既存データのID値と所属関係は維持する。
    LocationID = Column(Integer, ForeignKey("M_Locations.LocationID"), nullable=False)
    # 設備グループの表示名と画面での表示順。
    GroupName = Column(String(100), nullable=False)
    SortOrder = Column(Integer, nullable=False, default=0)


class Resource(AuditMixin, SoftDeleteMixin, Base):
    """リソースマスタ。設備名・能力・所属グループを管理し、拠点の勤務を使う。"""

    __tablename__ = "M_Resources"
    # 設備を識別する番号。稼働カレンダーはLocationIDから所属拠点を参照する。
    ResourceID = Column(Integer, primary_key=True, autoincrement=True)
    # 拠点の識別番号。既存データのID値と所属関係は維持する。
    LocationID = Column(Integer, ForeignKey("M_Locations.LocationID"), nullable=False)
    ResourceGroupID = Column(Integer, ForeignKey("M_ResourceGroups.ResourceGroupID"), nullable=True)
    # 設備の表示名。関連付けにはResourceIDを使う。
    ResourceName = Column(String(100), nullable=False)
    # 同時処理できる数量と、日単位の能力上限。
    Capacity = Column(Numeric(9, 2), nullable=False, default=1)
    DailyCapacityHours = Column(Numeric(5, 2), nullable=True)
    # 画面・ボードでの表示順。
    SortOrder = Column(Integer, nullable=False, default=0)


# ---------------------------------------------------------------- 設定
class AttributeDefinition(AuditMixin, Base):
    """属性定義マスタ"""

    __tablename__ = "M_AttributeDefinitions"
    __table_args__ = (
        UniqueConstraint("EntityType", "AttributeKey"),
        CheckConstraint(in_check("EntityType", ENTITY_TYPES), name="EntityType"),
        CheckConstraint(in_check("DataType", DATA_TYPES), name="DataType"),
    )
    AttributeDefID = Column(Integer, primary_key=True, autoincrement=True)
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


class ProductSwitchTime(AuditMixin, Base):
    """製品切替時間マスタ。属性と設備グループごとの切替条件をまとめる。"""

    __tablename__ = "M_ProductSwitchTimes"
    # 切替時間設定の識別番号。明細からの参照にも使う。
    ProductSwitchTimeID = Column(Integer, primary_key=True, autoincrement=True)
    # 拠点の識別番号。既存データのID値と所属関係は維持する。
    LocationID = Column(Integer, ForeignKey("M_Locations.LocationID"), nullable=False)
    # 切替時間設定の表示名と、切替の判定に使う属性。
    ProductSwitchTimeName = Column(String(100), nullable=False)
    AttributeKey = Column(String(50), nullable=False)
    ResourceGroupID = Column(Integer, ForeignKey("M_ResourceGroups.ResourceGroupID"), nullable=True)
    DefaultMinutes = Column(Integer, nullable=False, default=0)
    IsActive = Column(Boolean, nullable=False, default=True)

    # この設定に属する切替ルール。親の削除時に明細も削除する。
    rules = relationship("ProductSwitchRule", cascade="all, delete-orphan", lazy="selectin")


class ProductSwitchRule(AuditMixin, Base):
    """製品切替ルールマスタ。FromValue/ToValueの'*'は任意の値。"""

    __tablename__ = "M_ProductSwitchRules"
    __table_args__ = (UniqueConstraint("ProductSwitchTimeID", "FromValue", "ToValue"),)
    # 切替ルールの識別番号と、所属する切替時間設定。
    ProductSwitchRuleID = Column(Integer, primary_key=True, autoincrement=True)
    ProductSwitchTimeID = Column(
        Integer, ForeignKey("M_ProductSwitchTimes.ProductSwitchTimeID", ondelete="CASCADE"), nullable=False
    )
    FromValue = Column(String(50), nullable=False)
    ToValue = Column(String(50), nullable=False)
    SetupMinutes = Column(Integer, nullable=False, default=0)
    IsForbidden = Column(Boolean, nullable=False, default=False)
    Cost = Column(Numeric(12, 2), nullable=True)


class CalculationSetting(AuditMixin, Base):
    """計算設定マスタ。計算で優先する条件の重みと固定期間を保持する。"""

    __tablename__ = "M_CalculationSettings"
    __table_args__ = (CheckConstraint(in_check("TimeUnit", TIME_UNITS), name="TimeUnit"),)
    # 計算設定の識別番号。計画からの参照にも使う。
    CalculationSettingID = Column(Integer, primary_key=True, autoincrement=True)
    # 拠点の識別番号。既存データのID値と所属関係は維持する。
    LocationID = Column(Integer, ForeignKey("M_Locations.LocationID"), nullable=False)
    # 計算設定の表示名と、計算の時間単位。
    CalculationSettingName = Column(String(100), nullable=False)
    TimeUnit = Column(String(10), nullable=False, default="MINUTE")
    # 納期・段取りなどの評価の重み。計算時間の上限は設けない。
    ObjectiveWeightsJSON = Column(JSON, nullable=False, default=dict)
    FrozenWindowHours = Column(Integer, nullable=False, default=0)
    IsDefault = Column(Boolean, nullable=False, default=False)


# ---------------------------------------------------------------- テンプレート
class Product(AuditMixin, SoftDeleteMixin, Base):
    """製品マスタ"""

    # 製品の保存先。テーブル・列・モデルをProduct系の名称に揃える。
    __tablename__ = "M_Product"
    __table_args__ = (UniqueConstraint("LocationID", "ProductName"),)
    # 製品を識別する番号。既存データのID値と関連付けを維持する。
    ProductID = Column(Integer, primary_key=True, autoincrement=True)
    # 拠点の識別番号。既存データのID値と所属関係は維持する。
    LocationID = Column(Integer, ForeignKey("M_Locations.LocationID"), nullable=False)
    # 拠点内で製品を区別する名称。
    ProductName = Column(String(100), nullable=False)
    # 製品に直接属する工程。番号順にタスクへ展開する。
    processes = relationship(
        "ProductProcess", cascade="all, delete-orphan", order_by="ProductProcess.SequenceNumber", lazy="selectin"
    )


class ProductProcess(AuditMixin, Base):
    """製品に直接属する工程マスタ。"""

    __tablename__ = "M_ProductProcesses"
    __table_args__ = (UniqueConstraint("ProductID", "SequenceNumber"),)
    # 工程の識別番号と、その工程が属する製品。
    ProductProcessID = Column(Integer, primary_key=True, autoincrement=True)
    ProductID = Column(
        Integer, ForeignKey("M_Product.ProductID", ondelete="CASCADE"), nullable=False
    )
    # 製品内の実行順序と工程の表示名。
    SequenceNumber = Column(Integer, nullable=False)
    ProcessName = Column(String(100), nullable=False)
    # この工程が終わってから次工程を開始するまでの待ち時間。最大の未指定は上限なし。
    MinLagAfterMin = Column(Integer, nullable=False, default=0)
    MaxLagAfterMin = Column(Integer, nullable=True)

    # この工程を実行できる設備または設備グループと所要時間。
    resources = relationship(
        "ProductProcessResource", cascade="all, delete-orphan", lazy="selectin"
    )


class ProductProcessResource(AuditMixin, Base):
    """工程リソース候補マスタ — 工程を実行できるリソースまたはグループ。"""

    __tablename__ = "M_ProductProcessResources"
    __table_args__ = (
        CheckConstraint(
            "(ResourceID IS NULL AND ResourceGroupID IS NOT NULL) OR "
            "(ResourceID IS NOT NULL AND ResourceGroupID IS NULL)",
            name="ResourceOrGroup",
        ),
    )
    # 実行候補の識別番号と、その候補が属する工程。
    ProductProcessResourceID = Column(Integer, primary_key=True, autoincrement=True)
    ProductProcessID = Column(
        Integer, ForeignKey("M_ProductProcesses.ProductProcessID", ondelete="CASCADE"), nullable=False
    )
    # 設備またはグループのどちらか一方だけを指定する。
    ResourceID = Column(Integer, ForeignKey("M_Resources.ResourceID"), nullable=True)
    ResourceGroupID = Column(Integer, ForeignKey("M_ResourceGroups.ResourceGroupID"), nullable=True)
    # 所要時間は準備＋固定＋数量×単位当たり時間。優先度はタスク候補に引き継ぐ。
    SetupMinutes = Column(Integer, nullable=False, default=0)
    FixedMinutes = Column(Integer, nullable=False, default=0)
    MinutesPerUnit = Column(Numeric(12, 4), nullable=False, default=0)
    Priority = Column(Integer, nullable=False, default=1)


# ---------------------------------------------------------------- 作業者
class Worker(SoftDeleteMixin, Base):
    """作業者本人の情報。指定された5列だけを保持する。"""

    __tablename__ = "M_Workers"
    # 作業者の識別番号と所属拠点。
    WorkerID = Column(Integer, primary_key=True, autoincrement=True)
    LocationID = Column(Integer, ForeignKey("M_Locations.LocationID"), nullable=False)
    # 作業者名と、管理上の補足。
    WorkerName = Column(String(100), nullable=False)
    Remarks = Column(String(500), nullable=True)


class WorkerSkillMap(Base):
    """作業者と製品工程の担当可否・工程別日上限。全工程分の組合せを保存する。"""

    __tablename__ = "M_WorkerSkillMap"
    # 同じ担当関係を重複させず、設定する日上限は正の数量に限定する。
    __table_args__ = (
        UniqueConstraint("WorkerID", "ProductProcessID"),
        CheckConstraint("MaxDailyQuantity IS NULL OR MaxDailyQuantity > 0", name="MaxDailyQuantity"),
    )
    # 担当関係の識別番号と、作業者・製品工程への参照。
    WorkerSkillMapID = Column(Integer, primary_key=True, autoincrement=True)
    WorkerID = Column(Integer, ForeignKey("M_Workers.WorkerID"), nullable=False)
    ProductProcessID = Column(
        Integer, ForeignKey("M_ProductProcesses.ProductProcessID", ondelete="CASCADE"), nullable=False
    )
    # 新しい担当関係は不可から開始する。日上限のNULLは追加制限なし。
    CanExecute = Column(Boolean, nullable=False, default=False)
    MaxDailyQuantity = Column(Numeric(18, 3), nullable=True)
    # 担当不可の理由などを記録する補足。
    Remarks = Column(String(500), nullable=True)


class WorkerCalendar(AuditMixin, SoftDeleteMixin, Base):
    """作業者の週次勤務。1行で1曜日・同日内の1時間帯を表す。"""

    __tablename__ = "M_WorkerCalendars"
    # 既存カレンダーと同じ曜日番号と、同日内の勤務時刻だけを許可する。
    __table_args__ = (
        CheckConstraint("DayOfWeek BETWEEN 0 AND 6", name="DayOfWeek"),
        CheckConstraint("EndTime > StartTime", name="EndAfterStart"),
    )
    # ユーザー指定の列名で勤務行を識別し、作業者へ関連付ける。
    WorkerCalendarsID = Column(Integer, primary_key=True, autoincrement=True)
    WorkerID = Column(Integer, ForeignKey("M_Workers.WorkerID"), nullable=False)
    # 日曜0～土曜6の曜日と、日本時間の勤務開始・終了時刻。
    DayOfWeek = Column(SmallInteger, nullable=False)
    StartTime = Column(Time, nullable=False)
    EndTime = Column(Time, nullable=False)
    # 午前・午後などの勤務名。
    WorkName = Column(String(50), nullable=True)


class WorkerCalendarException(AuditMixin, Base):
    """作業者の不在日時。勤務行を経由して対象作業者を特定する。"""

    __tablename__ = "M_WorkerCalendarExceptions"
    # 日付を含め、終了が開始より後になる不在だけを保存する。
    __table_args__ = (CheckConstraint("EndAt > StartAt", name="EndAfterStart"),)
    # 不在行の識別番号と、対象作業者に属する勤務行。
    ExceptionID = Column(Integer, primary_key=True, autoincrement=True)
    WorkerCalendarsID = Column(
        Integer, ForeignKey("M_WorkerCalendars.WorkerCalendarsID", ondelete="CASCADE"), nullable=False
    )
    # 不在期間は日本時間の日時として保持し、複数日にまたがる不在も許可する。
    StartAt = Column(DateTime, nullable=False)
    EndAt = Column(DateTime, nullable=False)
    # ユーザー指定の単数形Remarkで不在理由を記録する。
    Remark = Column(String(500), nullable=True)

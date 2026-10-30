"""UI モックに合わせたデモデータ: 1 工場、配合 → 充填 → 包装。

日付は「翌日 06:00（拠点時刻）」を基準にするため、デモは常に直近の将来を計画する。
`DataBase/setup_database.py` から初期データ登録に使う。
"""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.timeutil import to_utc_naive
from app.models import masters as m
from app.models import transactions as t
from app.services.order_service import generate_tasks

TZ = "Asia/Tokyo"
USER = "seed"


def demo_start(now: datetime | None = None) -> datetime:
    """翌日 06:00（現地時刻）を naive な UTC で返す。"""
    local_now = (now or datetime.now(ZoneInfo(TZ))).astimezone(ZoneInfo(TZ))
    tomorrow = local_now.date() + timedelta(days=1)
    return to_utc_naive(datetime.combine(tomorrow, time(6, 0)), TZ)


def seed_demo(db: Session, now: datetime | None = None) -> dict[str, int]:
    org = m.Organization(OrganizationCode="DEMO", OrganizationName="Demo Co.", CreatedBy=USER)
    db.add(org)
    db.flush()
    # 対象の拠点情報。現地時刻や既定設定の参照に使う。
    location = m.Location(
        OrganizationID=org.OrganizationID, LocationCode="PLANT-A", LocationName="工場A",
        TimeZone=TZ, CreatedBy=USER,
    )
    db.add(location)
    db.flush()

    # 月〜土 06:00–12:00 と 13:00–22:00（昼休み 12–13）
    cal = m.Calendar(LocationID=location.LocationID, CalendarCode="STD", CalendarName="標準カレンダー", CreatedBy=USER)
    for dow in range(1, 7):
        cal.patterns.append(m.CalendarPattern(DayOfWeek=dow, StartTime=time(6), EndTime=time(12), ShiftName="午前"))
        cal.patterns.append(m.CalendarPattern(DayOfWeek=dow, StartTime=time(13), EndTime=time(22), ShiftName="午後"))
    db.add(cal)
    db.flush()
    location.DefaultCalendarID = cal.CalendarID

    groups = {}
    for i, (code, name) in enumerate([("MIX", "配合"), ("FIL", "充填"), ("PAC", "包装")]):
        g = m.ResourceGroup(LocationID=location.LocationID, GroupCode=code, GroupName=name, SortOrder=i, CreatedBy=USER)
        db.add(g)
        groups[code] = g
    db.flush()
    for i, (code, name, grp) in enumerate([
        ("M-01", "配合機 M-01", "MIX"), ("M-02", "配合機 M-02", "MIX"),
        ("F-01", "充填機 F-01", "FIL"), ("F-02", "充填機 F-02", "FIL"),
        ("P-01", "包装機 P-01", "PAC"), ("P-02", "包装機 P-02", "PAC"),
    ]):
        db.add(m.Resource(
            LocationID=location.LocationID, ResourceGroupID=groups[grp].ResourceGroupID, ResourceCode=code,
            ResourceName=name, ResourceType="MACHINE", Capacity=1, CalendarID=cal.CalendarID,
            SortOrder=i, CreatedBy=USER,
        ))

    db.add(m.AttributeDefinition(
        OrganizationID=org.OrganizationID, EntityType="ITEM", AttributeKey="family",
        Label="系統", DataType="ENUM", EnumValuesJSON=["A", "B", "C"], CreatedBy=USER,
    ))

    # 配合機の段取り替え（製品系統別）。同一系統は段取りなし。
    matrix = m.ChangeoverMatrix(
        LocationID=location.LocationID, MatrixName="配合 系統切替", AttributeKey="family",
        ResourceGroupID=groups["MIX"].ResourceGroupID, DefaultMinutes=0, CreatedBy=USER,
    )
    for frm, to, mins in [("A", "B", 30), ("A", "C", 45), ("B", "C", 30), ("B", "A", 90), ("C", "A", 120), ("C", "B", 60)]:
        matrix.entries.append(m.ChangeoverEntry(FromValue=frm, ToValue=to, SetupMinutes=mins))
    db.add(matrix)

    db.add(m.Rule(
        LocationID=location.LocationID, RuleTypeKey="allowed_weekdays", RuleName="系統Cは土曜生産しない",
        SelectorJSON={"family": "C"}, ParamsJSON={"weekdays": [1, 2, 3, 4, 5]}, IsHard=True,
        CreatedBy=USER,
    ))
    db.add(m.PlanProfile(
        LocationID=location.LocationID, ProfileName="納期優先", TimeUnit="MINUTE", IsDefault=True,
        ObjectiveWeightsJSON={"lateness": 1000, "setup": 10, "makespan": 1, "unscheduled": 100000},
        TimeLimitSec=30, CreatedBy=USER,
    ))

    # 3 工程の工程ルートを持つ品目。kg あたりの分は工程ごとに異なる。
    items = {}
    for code, fam in [("A-200", "A"), ("A-310", "A"), ("B-110", "B"), ("B-140", "B"), ("B-150", "B"), ("C-020", "C")]:
        item = m.Item(LocationID=location.LocationID, ItemCode=code, ItemName=f"品目 {code}", Unit="kg",
                      AttributesJSON={"family": fam}, CreatedBy=USER)
        db.add(item)
        db.flush()
        routing = m.Routing(ItemID=item.ItemID, RoutingName=f"{code} 標準", Revision=1, IsDefault=True, CreatedBy=USER)
        for no, name, grp, setup, mpu, lag in [
            (10, "配合", "MIX", 0, 0.12, 60),   # 充填までに 60 分の冷却
            (20, "充填", "FIL", 15, 0.10, 0),
            (30, "包装", "PAC", 10, 0.08, 0),
        ]:
            step = m.RoutingStep(StepNo=no, StepName=name, MinLagAfterMin=lag)
            step.resources.append(m.RoutingStepResource(
                ResourceGroupID=groups[grp].ResourceGroupID, SetupMinutes=setup, MinutesPerUnit=mpu,
            ))
            routing.steps.append(step)
        db.add(routing)
        items[code] = item
    db.flush()

    start = demo_start(now)
    orders = []
    for no, code, qty, due_h, prio in [
        ("JB-1041", "A-200", 1200, 30, 10), ("JB-1043", "B-110", 800, 33, 50),
        ("JB-1044", "C-020", 2000, 36, 50), ("JB-1045", "B-150", 600, 14, 10),
        ("JB-1046", "B-140", 900, 52, 50), ("JB-1047", "A-310", 1500, 10, 10),
        ("JB-1048", "B-110", 400, 51, 90),
    ]:
        order = t.Order(
            LocationID=location.LocationID, OrderNo=no, OrderName=f"{no} 品目 {code}", OrderType="ORDER",
            ItemID=items[code].ItemID, Quantity=qty, ReleaseAt=start,
            DueAt=start + timedelta(hours=due_h), Priority=prio, Status="OPEN", CreatedBy=USER,
        )
        db.add(order)
        orders.append(order)
    db.commit()
    for order in orders:
        generate_tasks(db, order, USER)
    return {"organizationId": org.OrganizationID, "locationId": location.LocationID, "orders": len(orders)}

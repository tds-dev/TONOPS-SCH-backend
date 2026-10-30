"""パン製造を模したデモデータ: 製品と「こねる → 焼く → 包装する」の工程ルート。

日付は「翌日 06:00（拠点時刻）」を基準にするため、デモは常に直近の将来を計画する。
`DataBase/setup_database.py` から初期データ登録に使う。
製造時間、発酵・冷却の待ち時間、段取り替えは仕組みを理解するための仮設定とする。
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


# パン製品・工程ルート・オーダーを含む新規デモデータを登録する。既存データは更新しない。
def seed_demo(db: Session, now: datetime | None = None) -> dict[str, int]:
    # DEMOコードは登録済み判定に使うため維持し、表示名をパン製造の例へ変更する。
    org = m.Organization(OrganizationCode="DEMO", OrganizationName="デモベーカリー", CreatedBy=USER)
    db.add(org)
    db.flush()
    # 対象の拠点情報。現地時刻や既定設定の参照に使う。
    location = m.Location(
        OrganizationID=org.OrganizationID, LocationCode="BAKERY-A", LocationName="パン工場",
        TimeZone=TZ, CreatedBy=USER,
    )
    db.add(location)
    db.flush()

    # パン工場のデモ稼働時間。月〜土06:00〜12:00・13:00〜18:00、日曜は休みとする。
    cal = m.Calendar(LocationID=location.LocationID, CalendarCode="STD", CalendarName="パン工場標準カレンダー", CreatedBy=USER)
    for dow in range(1, 7):
        cal.patterns.append(m.CalendarPattern(DayOfWeek=dow, StartTime=time(6), EndTime=time(12), ShiftName="午前"))
        cal.patterns.append(m.CalendarPattern(DayOfWeek=dow, StartTime=time(13), EndTime=time(18), ShiftName="午後"))
    db.add(cal)
    db.flush()
    location.DefaultCalendarID = cal.CalendarID

    # 工程ごとに使える設備の集合。各工程には同じグループの設備を候補として紐付ける。
    groups = {}
    for i, (code, name) in enumerate([("KNEAD", "こねる設備"), ("BAKE", "焼く設備"), ("PACK", "包装設備")]):
        g = m.ResourceGroup(LocationID=location.LocationID, GroupCode=code, GroupName=name, SortOrder=i, CreatedBy=USER)
        db.add(g)
        groups[code] = g
    db.flush()
    for i, (code, name, grp) in enumerate([
        ("KN-01", "ミキサー1号機", "KNEAD"), ("KN-02", "ミキサー2号機", "KNEAD"),
        ("OV-01", "オーブン1号機", "BAKE"), ("OV-02", "オーブン2号機", "BAKE"),
        ("PK-01", "包装機1号機", "PACK"), ("PK-02", "包装機2号機", "PACK"),
    ]):
        db.add(m.Resource(
            LocationID=location.LocationID, ResourceGroupID=groups[grp].ResourceGroupID, ResourceCode=code,
            ResourceName=name, ResourceType="MACHINE", Capacity=1, CalendarID=cal.CalendarID,
            SortOrder=i, CreatedBy=USER,
        ))

    db.add(m.AttributeDefinition(
        OrganizationID=org.OrganizationID, EntityType="PRODUCT", AttributeKey="family",
        Label="パンの分類", DataType="ENUM", EnumValuesJSON=["食事パン", "菓子パン", "ナッツ入り"], CreatedBy=USER,
    ))

    # パン分類を切り替える際の準備時間を表すデモ。同じ分類同士では追加の段取りを不要とする。
    matrix = m.ChangeoverMatrix(
        LocationID=location.LocationID, MatrixName="ミキサーのパン分類切替", AttributeKey="family",
        ResourceGroupID=groups["KNEAD"].ResourceGroupID, DefaultMinutes=0, CreatedBy=USER,
    )
    for frm, to, mins in [
        ("食事パン", "菓子パン", 10), ("食事パン", "ナッツ入り", 15),
        ("菓子パン", "食事パン", 10), ("菓子パン", "ナッツ入り", 15),
        ("ナッツ入り", "食事パン", 20), ("ナッツ入り", "菓子パン", 20),
    ]:
        matrix.entries.append(m.ChangeoverEntry(FromValue=frm, ToValue=to, SetupMinutes=mins))
    db.add(matrix)

    db.add(m.Rule(
        LocationID=location.LocationID, RuleTypeKey="allowed_weekdays", RuleName="くるみパンは平日のみ製造（デモ）",
        SelectorJSON={"family": "ナッツ入り"}, ParamsJSON={"weekdays": [1, 2, 3, 4, 5]}, IsHard=True,
        CreatedBy=USER,
    ))
    db.add(m.PlanProfile(
        LocationID=location.LocationID, ProfileName="パン製造・納期優先", TimeUnit="MINUTE", IsDefault=True,
        ObjectiveWeightsJSON={"lateness": 1000, "setup": 10, "makespan": 1, "unscheduled": 100000},
        TimeLimitSec=30, CreatedBy=USER,
    ))

    # 製品はパンそのもの。各製品の分類はタスクへ引き継がれ、制約・段取り替えの判定に使う。
    products = {}
    for code, name, fam in [
        ("BREAD-001", "食パン", "食事パン"), ("BREAD-002", "バターロール", "食事パン"),
        ("BREAD-003", "フランスパン", "食事パン"), ("BREAD-004", "あんパン", "菓子パン"),
        ("BREAD-005", "メロンパン", "菓子パン"), ("BREAD-006", "くるみパン", "ナッツ入り"),
    ]:
        product = m.Product(LocationID=location.LocationID, ProductCode=code, ProductName=name, Unit="個",
                      AttributesJSON={"family": fam}, CreatedBy=USER)
        db.add(product)
        db.flush()
        routing = m.Routing(ProductID=product.ProductID, RoutingName=f"{name}：こねる → 焼く → 包装する", Revision=1, IsDefault=True, CreatedBy=USER)
        # 工程は製品ごとのひな形、タスクはオーダーごとの実行単位。時間は準備＋固定＋数量×単位時間で求める。
        # こねた後の60分を発酵、焼いた後の30分を冷却として簡略表現する。
        for no, step_name, grp, setup, fixed, mpu, lag in [
            (10, "こねる", "KNEAD", 10, 20, 0.05, 60),
            (20, "焼く", "BAKE", 10, 25, 0.10, 30),
            (30, "包装する", "PACK", 5, 0, 0.15, 0),
        ]:
            step = m.RoutingStep(StepNo=no, StepName=step_name, MinLagAfterMin=lag)
            step.resources.append(m.RoutingStepResource(
                ResourceGroupID=groups[grp].ResourceGroupID, SetupMinutes=setup, FixedMinutes=fixed, MinutesPerUnit=mpu,
            ))
            routing.steps.append(step)
        db.add(routing)
        products[code] = product
    db.flush()

    # オーダーは店舗からの製造依頼。製品・個数・納期を指定し、同じルートから個別のタスクを作る。
    start = demo_start(now)
    orders = []
    for no, code, qty, due_h, prio, customer in [
        ("ORD-1001", "BREAD-001", 200, 8, 10, "駅前店"),
        ("ORD-1002", "BREAD-002", 300, 10, 30, "中央店"),
        ("ORD-1003", "BREAD-003", 150, 10, 30, "駅前店"),
        ("ORD-1004", "BREAD-004", 180, 12, 20, "中央店"),
        ("ORD-1005", "BREAD-005", 120, 12, 30, "北口店"),
        ("ORD-1006", "BREAD-006", 160, 58, 40, "北口店"),
        ("ORD-1007", "BREAD-001", 100, 32, 50, "中央店"),
    ]:
        # 製品名を表示用の名称へ使い、数量の単位は製品マスタの「個」と揃える。
        product = products[code]
        order = t.Order(
            LocationID=location.LocationID, OrderNo=no, OrderName=f"{product.ProductName} {qty}個（{customer}向け）", OrderType="ORDER",
            ProductID=product.ProductID, Quantity=qty, CustomerName=customer, ReleaseAt=start,
            DueAt=start + timedelta(hours=due_h), Priority=prio, Status="OPEN", CreatedBy=USER,
        )
        db.add(order)
        orders.append(order)
    db.commit()
    for order in orders:
        generate_tasks(db, order, USER)
    return {"organizationId": org.OrganizationID, "locationId": location.LocationID, "orders": len(orders)}

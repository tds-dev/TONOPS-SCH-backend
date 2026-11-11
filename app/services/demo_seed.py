"""パン製造を模したデモデータ: 製品・製品工程・店舗向けオーダー・下書き計画。

日付は「翌日 06:00（拠点時刻）」を基準にするため、デモは常に直近の将来を計画する。
`DataBase/setup_database.py` から初期データ登録に使う。
製造時間、発酵・冷却の待ち時間、段取り替えは仕組みを理解するための仮設定とする。
"""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.timeutil import to_jst_naive
from app.models import masters as m
from app.models import transactions as t
from app.services.order_service import generate_tasks
from app.services.plan_service import create_plan

# パン工場の現地時刻と、初期データの登録者。
TZ = get_settings().app_timezone
USER = "seed"
# 初期設定の登録済み判定と、デモ作成で共通に使う拠点名。
DEMO_LOCATION_NAME = "パン工場"

# 店舗向けの製造計画を想像できる名称。計画番号は名前に含めず、同じ拠点内で重複させない。
DEMO_PLAN_NAMES = ("各店舗向けパン製造・通常計画", "各店舗向けパン製造・見直し計画")


# 指定日または現在日の翌日06:00を、保存用の日本時間の日時へ変換する。
def demo_start(now: datetime | None = None) -> datetime:
    """翌日 06:00（現地時刻）を 時差情報なしの日本時間 で返す。"""
    local_now = (now or datetime.now(ZoneInfo(TZ))).astimezone(ZoneInfo(TZ))
    tomorrow = local_now.date() + timedelta(days=1)
    return to_jst_naive(datetime.combine(tomorrow, time(6, 0)))


# パン製品・製品工程・オーダー・下書き計画を含む新規デモデータを登録する。
def seed_demo(db: Session, now: datetime | None = None) -> dict[str, int]:
    # 組織を介さず、共通の拠点名で初期データを識別する。
    location = m.Location(LocationName=DEMO_LOCATION_NAME, CreatedBy=USER)
    db.add(location)
    db.flush()

    # パン工場のデモ稼働時間。月〜土06:00〜12:00・13:00〜18:00、日曜は休みとする。
    # 曜日番号は日曜0、月曜1～土曜6。月〜土の午前・午後を直接登録し、日曜は休みとする。
    calendars = []
    for dow in range(1, 7):
        for start_hour, end_hour, work_name in [(6, 12, "午前"), (13, 18, "午後")]:
            calendars.append(m.Calendar(
                LocationID=location.LocationID, DayOfWeek=dow, StartTime=time(start_hour),
                EndTime=time(end_hour), WorkName=work_name, CreatedBy=USER,
            ))
    db.add_all(calendars)
    db.flush()
    # 先頭の勤務行を代表とし、すべての勤務行を拠点共通として使う。
    location.CalendarID = calendars[0].CalendarID

    # 工程ごとに使える設備の集合。各工程には同じグループの設備を候補として紐付ける。
    groups = {}
    for i, (key, name) in enumerate([("KNEAD", "こねる設備"), ("BAKE", "焼く設備"), ("PACK", "包装設備")]):
        # keyはデモ作成中だけ使う参照名。DBには名前と識別番号を保存する。
        g = m.ResourceGroup(LocationID=location.LocationID, GroupName=name, SortOrder=i, CreatedBy=USER)
        db.add(g)
        groups[key] = g
    db.flush()
    for i, (name, grp) in enumerate([
        ("ミキサー1号機", "KNEAD"), ("ミキサー2号機", "KNEAD"),
        ("オーブン1号機", "BAKE"), ("オーブン2号機", "BAKE"),
        ("包装機1号機", "PACK"), ("包装機2号機", "PACK"),
    ]):
        db.add(m.Resource(
            LocationID=location.LocationID, ResourceGroupID=groups[grp].ResourceGroupID,
            ResourceName=name, ResourceType="MACHINE", Capacity=1, CalendarID=location.CalendarID,
            SortOrder=i, CreatedBy=USER,
        ))

    db.add(m.AttributeDefinition(
        EntityType="ORDER", AttributeKey="family",
        Label="パンの分類", DataType="ENUM", EnumValuesJSON=["食事パン", "菓子パン", "ナッツ入り"], CreatedBy=USER,
    ))

    # パン分類を切り替える際の準備時間を表すデモ。同じ分類同士では追加の段取りを不要とする。
    switch_time = m.ProductSwitchTime(
        LocationID=location.LocationID, ProductSwitchTimeName="ミキサーのパン分類切替", AttributeKey="family",
        ResourceGroupID=groups["KNEAD"].ResourceGroupID, DefaultMinutes=0, CreatedBy=USER,
    )
    for frm, to, mins in [
        ("食事パン", "菓子パン", 10), ("食事パン", "ナッツ入り", 15),
        ("菓子パン", "食事パン", 10), ("菓子パン", "ナッツ入り", 15),
        ("ナッツ入り", "食事パン", 20), ("ナッツ入り", "菓子パン", 20),
    ]:
        switch_time.rules.append(m.ProductSwitchRule(FromValue=frm, ToValue=to, SetupMinutes=mins))
    db.add(switch_time)

    db.add(m.Rule(
        LocationID=location.LocationID, RuleTypeKey="allowed_weekdays", RuleName="くるみパンは平日のみ製造（デモ）",
        SelectorJSON={"family": "ナッツ入り"}, ParamsJSON={"weekdays": [1, 2, 3, 4, 5]}, IsHard=True,
        CreatedBy=USER,
    ))
    db.add(m.CalculationSetting(
        LocationID=location.LocationID, CalculationSettingName="パン製造・納期優先", TimeUnit="MINUTE", IsDefault=True,
        ObjectiveWeightsJSON={"lateness": 1000, "setup": 10, "makespan": 1, "unscheduled": 100000},
        TimeLimitSec=30, CreatedBy=USER,
    ))

    # 製品は名称だけを管理し、工程を直接紐づける。
    products = {}
    # 分類は製品マスタには保存せず、後でデモオーダーの属性へ設定する。
    order_families = {}
    for name, family in [
        ("食パン", "食事パン"), ("バターロール", "食事パン"),
        ("フランスパン", "食事パン"), ("あんパン", "菓子パン"),
        ("メロンパン", "菓子パン"), ("くるみパン", "ナッツ入り"),
    ]:
        # この製品と、製品に直接属する工程のひな形。
        product = m.Product(LocationID=location.LocationID, ProductName=name, CreatedBy=USER)
        db.add(product)
        db.flush()
        # 工程は製品ごとのひな形、タスクはオーダーごとの実行単位。時間は準備＋固定＋数量×単位時間で求める。
        # こねた後の60分を発酵、焼いた後の30分を冷却として簡略表現する。
        for no, process_name, grp, setup, fixed, mpu, lag in [
            (1, "こねる", "KNEAD", 10, 20, 0.05, 60),
            (2, "焼く", "BAKE", 10, 25, 0.10, 30),
            (3, "包装する", "PACK", 5, 0, 0.15, 0),
        ]:
            # 工程の実行順序、工程名、次工程までの待ち時間。
            process = m.ProductProcess(SequenceNumber=no, ProcessName=process_name, MinLagAfterMin=lag, CreatedBy=USER)
            process.resources.append(m.ProductProcessResource(
                ResourceGroupID=groups[grp].ResourceGroupID, SetupMinutes=setup, FixedMinutes=fixed, MinutesPerUnit=mpu,
                CreatedBy=USER,
            ))
            product.processes.append(process)
        products[name] = product
        order_families[name] = family
    db.flush()

    # オーダーは店舗からの製造依頼。製品・個数・納期を指定し、製品工程から個別のタスクを作る。
    start = demo_start(now)
    orders = []
    for no, name, qty, due_h, prio, customer in [
        ("ORD-1001", "食パン", 200, 8, 10, "駅前店"),
        ("ORD-1002", "バターロール", 300, 10, 30, "中央店"),
        ("ORD-1003", "フランスパン", 150, 10, 30, "駅前店"),
        ("ORD-1004", "あんパン", 180, 12, 20, "中央店"),
        ("ORD-1005", "メロンパン", 120, 12, 30, "北口店"),
        ("ORD-1006", "くるみパン", 160, 58, 40, "北口店"),
        ("ORD-1007", "食パン", 100, 32, 50, "中央店"),
    ]:
        # 数量の「個」はデモの表示名に含める。分類属性はオーダーからタスクへ引き継ぐ。
        product = products[name]
        order = t.Order(
            LocationID=location.LocationID, WBSNumber=no, OrderName=f"{product.ProductName} {qty}個（{customer}向け）", OrderType="ORDER",
            ProductID=product.ProductID, Quantity=qty, CustomerName=customer, ReleaseAt=start,
            DeadLine=start + timedelta(hours=due_h), Priority=prio, Status="OPEN", CreatedBy=USER,
            AttributesJSON={"family": order_families[name]},
        )
        db.add(order)
        orders.append(order)
    db.commit()
    for order in orders:
        generate_tasks(db, order, USER)

    # 既存オーダーと同じ翌日06:00から3日間の下書きを、通常の名前検証を通して登録する。
    # 両方とも同じ計算条件で開始し、割付・評価値は画面で計算してから確認する。
    for plan_name in DEMO_PLAN_NAMES:
        create_plan(
            db, location_id=location.LocationID, horizon_start=start, horizon_end=start + timedelta(days=3),
            user=USER, plan_name=plan_name, use_master_as_base=False,
            remarks="駅前店・中央店・北口店向けの食パン・菓子パンなどの製造計画。",
        )
    return {"locationId": location.LocationID,
            "orders": len(orders), "plans": len(DEMO_PLAN_NAMES)}

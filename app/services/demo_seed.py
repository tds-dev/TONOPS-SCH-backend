"""パン製造を模したデモデータ: 製品・製品工程・作業者と勤務・オーダー・下書き計画。

比較撮影用に2026-11-16 06:00開始、5日間の割付と評価値を登録する。
`DataBase/setup_database.py` から初期データ登録に使う。
製造時間、発酵・冷却の待ち時間、段取り替えは仕組みを理解するための仮設定とする。
設備候補と工程間の待ち時間は製品マスタにだけ保存し、タスク生成時には複製しない。
"""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.timeutil import to_jst_naive
from app.models import masters as m
from app.models import transactions as t
from app.engine.evaluate import compute_kpis
from app.engine.result import SAssignment
from app.engine.snapshot import build_problem
from app.services.task_conditions import option_duration
from app.services.order_service import generate_tasks
from app.services.plan_service import create_plan
from app.services.worker_process_service import add_worker_skill_maps

# パン工場の現地時刻と、初期データの登録者。
TZ = get_settings().app_timezone
USER = "seed"
# 初期設定の登録済み判定と、デモ作成で共通に使う拠点名。
DEMO_LOCATION_NAME = "パン工場"

# 店舗向けの製造計画を想像できる名称。計画番号は名前に含めず、同じ拠点内で重複させない。
DEMO_PLAN_NAMES = ("11月第3週_パン製造計画", "11月第3週_パン製造計画v2")


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
            ResourceName=name, Capacity=1,
            SortOrder=i, CreatedBy=USER,
        ))

    # 設備グループごとの段取り替え設定。明細は工程IDの確定後に追加する。
    switch_time = m.ProductSwitchTime(
        LocationID=location.LocationID, ProductSwitchTimeName="ミキサーの製品工程切替条件",
        ResourceID=None, ResourceGroupID=groups["KNEAD"].ResourceGroupID, DefaultMinutes=0, CreatedBy=USER,
    )
    db.add(switch_time)
    # 単体指定の操作例。既存の有効なグループ設定と競合しないよう無効で登録する。
    db.flush()
    single_resource = db.scalar(select(m.Resource).where(
        m.Resource.LocationID == location.LocationID, m.Resource.SortOrder == 0,
    ))
    db.add(m.ProductSwitchTime(
        LocationID=location.LocationID, ProductSwitchTimeName="ミキサー1号機の切替条件（設定例）",
        ResourceID=single_resource.ResourceID, ResourceGroupID=None,
        DefaultMinutes=0, IsActive=False, CreatedBy=USER,
    ))

    db.add(m.CalculationSetting(
        LocationID=location.LocationID, CalculationSettingName="パン製造・納期優先", TimeUnit="MINUTE", IsDefault=True,
        ObjectiveWeightsJSON={"lateness": 1000, "setup": 10, "makespan": 1, "unscheduled": 100000},
        CreatedBy=USER,
    ))

    # 製品は品目コードと名称を管理し、工程を直接紐づける。
    products = {}
    # デモの曜日制限・段取り替え設定を組み立てる分類。DBには保存しない。
    product_families = {}
    for code, name, family in [
        ("BREAD-001", "食パン", "食事パン"), ("BREAD-002", "バターロール", "食事パン"),
        ("BREAD-003", "フランスパン", "食事パン"), ("BREAD-004", "あんパン", "菓子パン"),
        ("BREAD-005", "メロンパン", "菓子パン"), ("BREAD-006", "くるみパン", "ナッツ入り"),
    ]:
        # この製品と、製品に直接属する工程のひな形。
        product = m.Product(LocationID=location.LocationID, ProductName=name, ProductCode=code, CreatedBy=USER)
        db.add(product)
        db.flush()
        # 工程は製品ごとのひな形、タスクはオーダーごとの実行単位。時間は準備＋固定＋数量×単位時間で求める。
        # こねた後の60分を発酵、焼いた後の30分を冷却として簡略表現する。
        for no, process_name, grp, setup, fixed, processing, lag in [
            (1, "こねる", "KNEAD", 10, 20, 0.05, 60),
            (2, "焼く", "BAKE", 10, 25, 0.10, 30),
            (3, "包装する", "PACK", 5, None, 0.15, 0),
        ]:
            # 工程の実行順序、共通作業時間、次工程までの待ち時間。
            process = m.ProductProcess(
                SequenceNumber=no, ProcessName=process_name, MinLagAfterMin=lag, CreatedBy=USER,
                SetupMinutes=setup, FixedMinutes=fixed, ProcessingMinutes=processing,
                AllowedWeekdaysJSON=[1, 2, 3, 4, 5] if family == "ナッツ入り" else list(range(7)),
            )
            process.resources.append(m.ProductProcessResource(
                ResourceGroupID=groups[grp].ResourceGroupID,
                CreatedBy=USER,
            ))
            product.processes.append(process)
        products[name] = product
        product_families[product.ProductID] = family
    db.flush()

    # 既存の分類間の仮設定を、各製品の「こねる」工程のIDに展開する。
    knead_processes = [process for product in products.values() for process in product.processes if process.SequenceNumber == 1]
    switch_minutes = {("食事パン", "菓子パン"): 10, ("食事パン", "ナッツ入り"): 15,
                      ("菓子パン", "食事パン"): 10, ("菓子パン", "ナッツ入り"): 15,
                      ("ナッツ入り", "食事パン"): 20, ("ナッツ入り", "菓子パン"): 20}
    for before in knead_processes:
        for after in knead_processes:
            # 工程から製品のデモ分類を取得し、異なる分類間の22組だけを登録する。
            minutes = switch_minutes.get((product_families[before.ProductID], product_families[after.ProductID]))
            if minutes is not None:
                switch_time.rules.append(m.ProductSwitchRule(
                    FromProductProcessID=before.ProductProcessID, ToProductProcessID=after.ProductProcessID,
                    SetupMinutes=minutes,
                ))
    db.flush()

    # 作業者と不在の基準日。既存オーダーと同じ翌日06:00を使用する。
    # SQL版と同じ撮影期間に固定し、実行日によって比較画面の日付が変わらないようにする。
    start = datetime(2026, 11, 16, 6, 0)
    # デモ作業者ごとの担当工程番号と、その工程での1日生産上限。
    worker_profiles = [("作業者A（こねる担当）", 1, 600),
                       ("作業者B（焼く担当）", 2, 600),
                       ("作業者C（包装担当）", 3, 1200)]
    # 作業者本人と、初期の担当値を付けるためのID別設定。
    workers = []
    worker_settings = {}
    for name, sequence, daily_limit in worker_profiles:
        # 指定5列の作業者モデル。登録者・日時の列は持たせない。
        worker = m.Worker(LocationID=location.LocationID, WorkerName=name, Remarks="パン製造デモの作業者")
        db.add(worker)
        db.flush()
        workers.append(worker)
        worker_settings[worker.WorkerID] = (sequence, daily_limit)
    # 全作業者×全製品工程のリンク件数。担当不可の行も省略せず登録する。
    worker_link_count = 0
    for product in products.values():
        for process in product.processes:
            for link in add_worker_skill_maps(db, process):
                # 工程番号が担当と一致する場合だけ、能力上限を付けて担当可能にする。
                sequence, daily_limit = worker_settings[link.WorkerID]
                link.CanExecute = process.SequenceNumber == sequence
                link.MaxDailyQuantity = daily_limit if link.CanExecute else None
                link.Remarks = None if link.CanExecute else "担当外（デモ）"
                worker_link_count += 1
    # 各作業者の月～土の午前・午後勤務。拠点の勤務とは独立した行として保持する。
    worker_calendars = []
    for worker in workers:
        for dow in range(1, 7):
            for start_hour, end_hour, work_name in [(6, 12, "午前"), (13, 18, "午後")]:
                worker_calendars.append(m.WorkerCalendar(
                    WorkerID=worker.WorkerID, DayOfWeek=dow, StartTime=time(start_hour),
                    EndTime=time(end_hour), WorkName=work_name, CreatedBy=USER,
                ))
    db.add_all(worker_calendars)
    db.flush()
    # 作業者Aの例外休日を本人へ直接登録する。計画計算への適用は行わない。
    db.add(m.WorkerCalendarException(
        WorkerID=workers[0].WorkerID,
        StartAt=start.replace(hour=10), EndAt=start.replace(hour=11), Remark="研修（デモ）", CreatedBy=USER,
    ))

    # オーダーは店舗からの製造依頼。製品・個数・納期を指定し、製品工程から個別のタスクを作る。
    # 複数指定・単一指定・未指定を確認する仮データ。作業者指定はまだ計算に反映しない。
    order_workers = {
        "WBS-1001": [workers[0].WorkerID, workers[1].WorkerID],
        "WBS-1002": [workers[1].WorkerID, workers[2].WorkerID],
        "WBS-1003": [workers[2].WorkerID],
    }
    orders = []
    for no, name, qty, due_h, prio, customer in [
        ("WBS-1001", "食パン", 200, 8, 10, "駅前店"),
        ("WBS-1002", "バターロール", 300, 10, 30, "中央店"),
        ("WBS-1003", "フランスパン", 150, 10, 30, "駅前店"),
        ("WBS-1004", "あんパン", 180, 12, 20, "中央店"),
        ("WBS-1005", "メロンパン", 120, 12, 30, "北口店"),
        ("WBS-1006", "くるみパン", 160, 58, 40, "北口店"),
        ("WBS-1007", "食パン", 100, 32, 50, "中央店"),
    ]:
        # 数量の「個」はデモの表示名に含める。分類属性はオーダーへ保存しない。
        product = products[name]
        order = t.Order(
            LocationID=location.LocationID, WBSNumber=no, OrderName=f"{product.ProductName} {qty}個（{customer}向け）",
            worker_links=[t.OrderWorker(WorkerID=worker_id) for worker_id in order_workers.get(no, [])],
            ProductID=product.ProductID, Quantity=qty, CustomerName=customer, ReleaseAt=start,
            DeadLine=start + timedelta(hours=due_h), Priority=prio, Status="OPEN", CreatedBy=USER,
        )
        db.add(order)
        orders.append(order)
    db.commit()
    for order in orders:
        generate_tasks(db, order, USER)

    # 5日間の下書きと撮影用の割付・評価値を登録する。
    plans = []
    for plan_name in DEMO_PLAN_NAMES:
        plan = create_plan(
            db, location_id=location.LocationID, start_at=start, end_at=start + timedelta(days=5),
            user=USER, plan_name=plan_name, use_master_as_base=False,
            remarks="駅前店・中央店・北口店向けの食パン・菓子パンなどの製造計画。",
        )
        plans.append(plan)
    # IDの固定値には依存せず、SQL版のタスク番号・設備番号を登録順に対応させる。
    tasks = db.scalars(select(t.Task).where(t.Task.OrderID.in_([order.OrderID for order in orders]))
                       .order_by(t.Task.OrderID, t.Task.Sequence)).all()
    resources = db.scalars(select(m.Resource).where(m.Resource.LocationID == location.LocationID)
                           .order_by(m.Resource.SortOrder)).all()
    # SQL版と同じ手動作成の撮影用割付。ソルバーは実行しない。
    slots = [
        (1, 1, 1, 2880, 0),
        (1, 2, 3, 3000, 0),
        (1, 3, 5, 3090, 0),
        (1, 4, 1, 2930, 0),
        (1, 5, 3, 3060, 0),
        (1, 6, 5, 3160, 0),
        (1, 7, 1, 2980, 0),
        (1, 8, 3, 3130, 0),
        (1, 9, 5, 3210, 0),
        (1, 10, 1, 3040, 10),
        (1, 11, 3, 3300, 0),
        (1, 12, 5, 3390, 0),
        (1, 13, 1, 3090, 0),
        (1, 14, 3, 3360, 0),
        (1, 15, 5, 3450, 0),
        (1, 16, 1, 3315, 15),
        (1, 17, 3, 3435, 0),
        (1, 18, 5, 3525, 0),
        (2, 1, 1, 0, 0),
        (2, 2, 3, 120, 0),
        (2, 3, 5, 210, 0),
        (2, 4, 1, 50, 0),
        (2, 5, 3, 180, 0),
        (2, 6, 5, 280, 0),
        (2, 7, 1, 100, 0),
        (2, 8, 3, 250, 0),
        (2, 9, 5, 330, 0),
        (2, 10, 2, 0, 0),
        (2, 11, 4, 120, 0),
        (2, 12, 6, 210, 0),
        (2, 13, 2, 50, 0),
        (2, 14, 4, 180, 0),
        (2, 15, 6, 260, 0),
        (2, 16, 1, 2895, 15),
        (2, 17, 3, 3015, 0),
        (2, 18, 5, 3105, 0),
        (2, 19, 1, 150, 0),
        (2, 20, 4, 260, 0),
        (2, 21, 5, 390, 0),
    ]
    assignments = {plan.PlanID: [] for plan in plans}
    for plan_number, task_number, resource_number, minute, setup in slots:
        plan, task, resource = plans[plan_number - 1], tasks[task_number - 1], resources[resource_number - 1]
        process = db.get(m.ProductProcess, task.ProductProcessID)
        order = db.get(t.Order, task.OrderID)
        duration = option_duration(process.SetupMinutes, process.FixedMinutes, process.ProcessingMinutes, order.Quantity)
        db.add(t.PlanAssignment(
            PlanID=plan.PlanID, TaskID=task.TaskID, ResourceID=resource.ResourceID,
            # 必須列を満たす仮の担当者。通常の計算・配置・コピー処理へは接続しない。
            WorkerID=workers[process.SequenceNumber - 1].WorkerID,
            StartAt=start + timedelta(minutes=minute), EndAt=start + timedelta(minutes=minute + duration),
            SetupMinutes=setup, Units=1, IsLocked=False, Source="IMPORT", CreatedBy=USER,
        ))
        assignments[plan.PlanID].append(SAssignment(task.TaskID, resource.ResourceID, minute, minute + duration, setup))
    db.flush()
    # 本番と同じ評価関数を使い、5日間の勤務時間と割付から7指標を求める。
    for plan in plans:
        for key, value in compute_kpis(build_problem(db, plan), assignments[plan.PlanID]).items():
            db.add(t.PlanKpi(PlanID=plan.PlanID, KpiKey=key, KpiValue=value))
    db.commit()
    return {"locationId": location.LocationID,
            "orders": len(orders), "plans": len(DEMO_PLAN_NAMES),
            "workers": len(workers), "workerSkillMaps": worker_link_count,
            "workerCalendars": len(worker_calendars), "workerCalendarExceptions": 1}

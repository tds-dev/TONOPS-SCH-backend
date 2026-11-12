"""実DB・設定ファイル・外部通信を使わず、オーダー・カレンダーCRUDと既存データの保持を確認するテスト。"""
import asyncio
import json
import unittest
from datetime import datetime
from unittest.mock import patch

from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.config import Settings

# .envを読まず、テスト専用のメモリDBと操作者を設定する。
with patch("app.core.config.get_settings", return_value=Settings(
    _env_file=None, database_url="sqlite:///:memory:", default_user="order-test",
)):
    from app.core.db import Base, get_db, make_engine
    from app.models.masters import Calendar, CalendarException, Location, Product, ProductProcess, ProductProcessResource, CalculationSetting, Resource, ResourceGroup
    from app.models.masters import Worker, WorkerSkillMap
    from app.models.transactions import WorkActual, Order, Plan, PlanAssignment, Task
    from app.routers.orders import routers
    from app.routers.masters import routers as master_routers


# 実際のHTTP接続を開かず、FastAPIの受付処理へリクエストを渡す。
async def request(app, method, path, body=None):
    # リクエストとレスポンスの本文を保持する。
    payload = json.dumps(body).encode() if body is not None else b""
    messages = []

    # ASGIへ本文を1回だけ渡す受信処理。
    async def receive():
        return {"type": "http.request", "body": payload, "more_body": False}

    # ASGIが返したステータスと本文を記録する送信処理。
    async def send(message):
        messages.append(message)

    # URLのパスと検索条件を分離する。
    route, _, query = path.partition("?")
    await app({"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": method,
               "scheme": "http", "path": route, "raw_path": route.encode(), "query_string": query.replace("+", "%2B").encode(),
               "headers": [(b"content-type", b"application/json")], "server": ("test", 80), "client": ("test", 1),
               "root_path": ""}, receive, send)
    # 分割された本文をまとめ、APIの返却値を読み取る。
    status = next(message["status"] for message in messages if message["type"] == "http.response.start")
    content = b"".join(message.get("body", b"") for message in messages if message["type"] == "http.response.body")
    return status, json.loads(content) if content else None


# オーダーとカレンダーのテストで、通信不要のAPIと独立したメモリDBを共用する。
class InMemoryApiTestCase(unittest.TestCase):
    # テストごとにDB・APIと、別拠点の混入を確認するための2拠点を準備する。
    def setUp(self):
        self.engine = make_engine("sqlite:///:memory:", poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine, expire_on_commit=False)
        self.app = FastAPI()
        for router in routers:
            self.app.include_router(router, prefix="/api/v1")
        for router in master_routers:
            self.app.include_router(router, prefix="/api/v1")
        self.app.dependency_overrides[get_db] = lambda: self.db
        # 組織に依存せず、別拠点のデータが混ざらない確認用の2拠点を作る。
        self.db.add_all([Location(LocationID=1, LocationName="拠点A"),
                         Location(LocationID=2, LocationName="拠点B")])
        self.db.commit()

    # テスト用のDBを閉じ、次のテストへデータを持ち越さない。
    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    # APIへ通信を発生させずに問い合わせる共通処理。
    def call(self, method, path, body=None):
        return asyncio.run(request(self.app, method, "/api/v1" + path, body))


# 登録から削除までの実APIと、誤入力・既存計画への影響を確認する。
class OrderCrudTest(InMemoryApiTestCase):
    # 共通の2拠点へ、オーダーの登録・タスク生成に必要な製品と工程を追加する。
    def setUp(self):
        super().setUp()
        self.db.add_all([Product(ProductID=1, LocationID=1, ProductName="製品A"),
                         Product(ProductID=2, LocationID=2, ProductName="製品B")])
        self.db.flush()
        self.db.add(ProductProcess(ProductProcessID=1, ProductID=1, SequenceNumber=1, ProcessName="製造"))
        self.db.commit()

    # 最小限の有効なオーダーを登録し、必要な項目だけ上書きする。
    def create(self, **values):
        body = {"locationId": 1, "wbsNumber": "ORD-001", "orderName": "製造依頼", "productId": 1, **values}
        status, order = self.call("POST", "/orders", body)
        self.assertEqual(status, 201, order)
        return order

    # CRUD全体と、論理削除後に番号・タスク・別オーダーが保持されることを確認する。
    def test_crud_preserves_unedited_data_and_tasks(self):
        self.create(wbsNumber="OTHER")
        order = self.create(quantity=12.345,
                            releaseAt="2026-10-30T09:00:00+09:00", deadLine="2026-10-30T12:00:00+09:00",
                            shippingDate="2026-10-30T15:00:00+09:00")
        order_id = order["orderId"]
        self.assertEqual(order["releaseAt"], "2026-10-30T09:00:00+09:00")
        self.assertEqual(order["shippingDate"], "2026-10-30T15:00:00+09:00")
        # 廃止した親オーダーID・種別・計画の管理元・属性をAPIへ返さない。
        for key in ("parentOrderId", "orderType", "planOwner", "attributesJSON"):
            self.assertNotIn(key, order)
        self.assertEqual(order["priority"], 50)
        self.assertEqual(order["createdBy"], "order-test")
        self.assertEqual(self.call("GET", f"/orders/{order_id}")[0], 200)
        status, tasks = self.call("POST", f"/orders/{order_id}/generate-tasks")
        self.assertEqual(status, 200, tasks)
        self.assertEqual(len(tasks), 1)
        # タスクの親階層・マイルストーン・工数の旧項目をAPIへ返さない。
        for key in ("parentTaskId", "isMilestone", "effortHours"):
            self.assertNotIn(key, tasks[0])
        status, updated = self.call("PATCH", f"/orders/{order_id}", {"orderName": "変更後", "remarks": "備考"})
        self.assertEqual(status, 200, updated)
        for key in ("productId", "quantity", "releaseAt", "deadLine", "shippingDate", "createdAt"):
            self.assertEqual(updated[key], order[key])
        self.assertEqual(updated["orderName"], "変更後")
        self.assertEqual(updated["updatedBy"], "order-test")
        self.assertEqual(self.call("DELETE", f"/orders/{order_id}")[0], 204)
        self.assertEqual(self.call("GET", f"/orders/{order_id}")[0], 404)
        self.assertTrue(self.db.get(Order, order_id).DeleteFlag)
        self.assertEqual(len(self.db.scalars(select(Task).where(Task.OrderID == order_id)).all()), 1)
        self.assertEqual(len(self.call("GET", "/orders?locationId=1")[1]), 1)
        self.assertEqual(len(self.call("GET", "/orders?locationId=1&includeDeleted=true")[1]), 2)

    # 削除した列がDBとAPIの登録・更新・応答の定義に残らないことを確認する。
    def test_removed_order_columns_are_absent_from_database_and_api(self):
        # APIが公開するオーダーの3種類の項目定義。
        schemas = self.app.openapi()["components"]["schemas"]
        for column, field in (("OrderType", "orderType"), ("PlanOwner", "planOwner"), ("AttributesJSON", "attributesJSON")):
            with self.subTest(column=column):
                self.assertNotIn(column, Order.__table__.columns)
                for name in ("OrderCreate", "OrderUpdate", "OrderRead"):
                    self.assertNotIn(field, schemas[name]["properties"])

    # オーダーを編集しても、タスクへ直接登録した既存属性を保持する。
    def test_order_edit_preserves_existing_task_attributes(self):
        # 属性を持たないオーダーから生成したタスクへ、作業固有の分類を設定する。
        order = self.create()
        status, tasks = self.call("POST", f'/orders/{order["orderId"]}/generate-tasks')
        self.assertEqual(status, 200, tasks)
        task_id = tasks[0]["taskId"]
        self.assertEqual(self.call("PATCH", f"/tasks/{task_id}", {"attributesJSON": {"family": "A"}})[0], 200)
        self.assertEqual(self.call("PATCH", f'/orders/{order["orderId"]}', {"orderName": "変更後"})[0], 200)
        self.assertEqual(self.call("GET", f'/orders/{order["orderId"]}/tasks')[1][0]["attributesJSON"], {"family": "A"})

    # 無効な値を保存せず、必須・範囲・所属・日時・選択値を確認する。
    def test_rejects_invalid_create(self):
        for values in ({"wbsNumber": "  "}, {"orderName": "x" * 201}, {"quantity": -1}, {"quantity": 0.0001},
                       {"quantity": 1e15}, {"priority": 0}, {"priority": None}, {"status": "UNKNOWN"},
                       {"productId": 2}, {"locationId": 999},
                       {"releaseAt": "2026-10-30T21:00:00+09:00", "deadLine": "2026-10-30T20:00:00+09:00"}):
            with self.subTest(values=values):
                status, result = self.call("POST", "/orders", {"locationId": 1, "wbsNumber": "INVALID", "orderName": "依頼", **values})
                self.assertEqual(status, 422, result)
                self.assertIsNone(self.db.scalar(select(Order.OrderID)))

    # 既存値と変更値を合わせた日時の前後関係と、所属拠点変更を拒否する。
    def test_partial_update_uses_existing_values(self):
        order = self.create(releaseAt="2026-10-30T18:00:00+09:00", deadLine="2026-10-30T21:00:00+09:00")
        for values in ({"deadLine": "2026-10-30T17:00:00+09:00"}, {"locationId": 2}, {"orderName": None}):
            with self.subTest(values=values):
                self.assertEqual(self.call("PATCH", f'/orders/{order["orderId"]}', values)[0], 422)
        self.assertEqual(self.call("PATCH", f'/orders/{order["orderId"]}', {"deadLine": None})[0], 200)
        # 任意の出荷日時は、日時を入力した後でも空欄へ戻せる。
        self.assertEqual(self.call("PATCH", f'/orders/{order["orderId"]}', {"shippingDate": None})[0], 200)

    # 削除済み番号も重複扱いとし、DBの不明瞭な制約エラーを避ける。
    def test_duplicate_numbers_include_deleted_orders(self):
        order = self.create()
        self.assertEqual(self.call("DELETE", f'/orders/{order["orderId"]}')[0], 204)
        self.assertEqual(self.call("POST", "/orders", {"locationId": 1, "wbsNumber": "ORD-001", "orderName": "重複"})[0], 409)
        self.assertEqual(self.create(locationId=2, productId=2)["locationId"], 2)

    # 計画に割付済みのタスクがある場合も、名称編集・履歴を残す削除は維持する。
    def test_planned_tasks_are_protected_and_history_survives_delete(self):
        order = self.create(quantity=10.123)
        order_id = order["orderId"]
        status, tasks = self.call("POST", f"/orders/{order_id}/generate-tasks")
        self.assertEqual(status, 200, tasks)
        self.db.add_all([CalculationSetting(CalculationSettingID=1, LocationID=1, CalculationSettingName="標準"),
                         Resource(ResourceID=1, LocationID=1, ResourceName="設備")])
        self.db.flush()
        self.db.add(Plan(PlanID=1, LocationID=1, PlanName="計画", CalculationSettingID=1,
                         StartAt=datetime(2026, 10, 30), EndAt=datetime(2026, 10, 31)))
        self.db.flush()
        self.db.add(PlanAssignment(PlanID=1, TaskID=tasks[0]["taskId"], ResourceID=1,
                                   StartAt=datetime(2026, 10, 30, 9), EndAt=datetime(2026, 10, 30, 10)))
        self.db.commit()
        # 設備名などの既存情報を返し、廃止した単価と設備属性を含めない。
        status, resource = self.call("GET", "/resources/1")
        self.assertEqual(status, 200, resource)
        self.assertEqual(resource["resourceName"], "設備")
        for key in ("costPerHour", "attributesJSON"):
            self.assertNotIn(key, resource)
        self.assertEqual(self.call("PATCH", f"/orders/{order_id}", {"quantity": 20})[0], 409)
        self.assertEqual(self.call("PATCH", f"/orders/{order_id}", {"quantity": 10.123})[0], 200)
        self.assertEqual(self.call("PATCH", f"/orders/{order_id}", {"remarks": "編集可"})[0], 200)
        self.assertEqual(self.call("POST", f"/orders/{order_id}/generate-tasks?replace=true")[0], 409)
        self.assertEqual(self.call("DELETE", f"/orders/{order_id}")[0], 204)
        self.assertIsNotNone(self.db.scalar(select(PlanAssignment.AssignmentID)))
        self.assertIsNotNone(self.db.get(Task, tasks[0]["taskId"]))

    # 実績または開始済みタスクがある場合も生成元を保護する。
    def test_actual_and_started_tasks_block_source_changes(self):
        order = self.create(quantity=10)
        order_id = order["orderId"]
        self.db.add(Task(TaskID=1, OrderID=order_id, TaskNo="10", TaskName="製造", Status="IN_PROGRESS"))
        self.db.commit()
        self.assertEqual(self.call("PATCH", f"/orders/{order_id}", {"quantity": 20})[0], 409)
        self.db.get(Task, 1).Status = "NOT_STARTED"
        self.db.add(WorkActual(TaskID=1, Status="DONE", StartAt=datetime(2026, 10, 30, 6), EndAt=datetime(2026, 10, 30, 7)))
        self.db.commit()
        self.assertEqual(self.call("PATCH", f"/orders/{order_id}", {"quantity": 20})[0], 409)
        self.assertEqual(self.call("DELETE", f"/orders/{order_id}")[0], 204)
        self.assertIsNotNone(self.db.scalar(select(WorkActual.WorkActualID)))
        self.assertIsNotNone(self.db.get(Task, 1))

    # 未割付のタスクは、既存の再生成操作で変更した数量を反映できる。
    def test_unplanned_order_can_update_and_regenerate(self):
        order = self.create(quantity=10)
        order_id = order["orderId"]
        self.assertEqual(self.call("POST", f"/orders/{order_id}/generate-tasks")[0], 200)
        self.assertEqual(self.call("PATCH", f"/orders/{order_id}", {"quantity": 20})[0], 200)
        self.assertEqual(self.call("POST", f"/orders/{order_id}/generate-tasks?replace=true")[0], 200)
        self.assertEqual(self.call("GET", f"/orders/{order_id}/dependencies")[0], 200)

    # 名称だけの製品マスタでも登録・編集・削除が使えることを確認する。
    def test_other_crud_keeps_existing_behavior(self):
        status, product = self.call("POST", "/products", {"locationId": 1, "productName": "新製品"})
        self.assertEqual(status, 201, product)
        self.assertEqual(self.call("PATCH", f'/products/{product["productId"]}', {"productName": "更新"})[0], 200)
        self.assertEqual(self.call("DELETE", f'/products/{product["productId"]}')[0], 204)

    # 既存の製品が削除済みでも、参照を変えない名称編集は妨げない。
    def test_deleted_master_references_are_preserved(self):
        order = self.create()
        self.db.get(Product, 1).DeleteFlag = True
        self.db.commit()
        status, updated = self.call("PATCH", f'/orders/{order["orderId"]}', {"orderName": "参照を保持"})
        self.assertEqual(status, 200, updated)
        self.assertEqual(updated["productId"], 1)
        self.assertNotIn("routingId", updated)
        self.assertEqual(self.call("POST", "/orders", {"locationId": 1, "wbsNumber": "NEW", "orderName": "無効参照", "productId": 1})[0], 422)

    # 廃止したルート・製品コード・単位・製品属性をAPIへ返さないことを確認する。
    def test_product_contract_has_no_route_or_removed_fields(self):
        # 新しい製品・オーダーの応答に含まれる項目。
        status, product = self.call("GET", "/products/1")
        self.assertEqual(status, 200, product)
        for key in ("productCode", "unit", "attributesJSON"):
            self.assertNotIn(key, product)
        self.assertNotIn("routingId", self.create())
        self.assertEqual(self.call("GET", "/routings")[0], 404)
        self.assertEqual(self.call("GET", "/routing-steps")[0], 404)
        self.assertEqual(self.call("GET", "/routing-step-resources")[0], 404)

    # 製品名は拠点内で重複させず、別拠点なら同じ名称を登録できることを確認する。
    def test_product_names_are_unique_within_location(self):
        self.assertEqual(self.call("POST", "/products", {"locationId": 1, "productName": " 製品A "})[0], 409)
        self.assertEqual(self.call("POST", "/products", {"locationId": 2, "productName": "製品A"})[0], 201)
        self.assertEqual(self.call("POST", "/products", {"locationId": 1, "productName": " "})[0], 422)

    # 指定位置への追加と、待ち時間・工程番号の入力範囲を確認する。
    def test_process_api_validates_sequence_and_waits(self):
        # 同じ製品に追加する工程の入力内容。
        body = {"productId": 1, "sequenceNumber": 2, "processName": "仕上げ", "minLagAfterMin": 5, "maxLagAfterMin": 10}
        status, process = self.call("POST", "/product-processes", body)
        self.assertEqual(status, 201, process)
        self.assertEqual(process["productId"], 1)
        self.assertIn("productProcessId", process)
        self.assertNotIn("attributesJSON", process)
        self.assertEqual(self.call("POST", "/product-processes", body)[0], 201)
        self.assertEqual(self.call("POST", "/product-processes", {**body, "productId": 2, "sequenceNumber": 1})[0], 201)
        self.assertEqual(self.call("PATCH", f'/product-processes/{process["productProcessId"]}', {"maxLagAfterMin": 4})[0], 422)
        self.assertEqual(self.call("PATCH", f'/product-processes/{process["productProcessId"]}', {"sequenceNumber": 0})[0], 422)

    # 工程の追加だけで全有効作業者分を作り、更新・再生成で既存の担当値を保持する。
    def test_new_process_adds_worker_links_and_preserves_existing_settings(self):
        # 同じ拠点の2人、別拠点の1人、削除済み1人を用意する。
        self.db.add_all([
            Worker(WorkerID=1, LocationID=1, WorkerName="作業者A"),
            Worker(WorkerID=2, LocationID=1, WorkerName="作業者B"),
            Worker(WorkerID=3, LocationID=2, WorkerName="別拠点"),
            Worker(WorkerID=4, LocationID=1, WorkerName="削除済み", DeleteFlag=True),
        ])
        self.db.commit()
        # 既存の製品工程APIを使い、追加した工程だけに担当リンクが生成されることを確認する。
        status, process = self.call("POST", "/product-processes", {
            "productId": 1, "sequenceNumber": 2, "processName": "担当確認工程",
        })
        self.assertEqual(status, 201, process)
        process_id = process["productProcessId"]
        links = self.db.scalars(select(WorkerSkillMap).where(
            WorkerSkillMap.ProductProcessID == process_id,
        ).order_by(WorkerSkillMap.WorkerID)).all()
        self.assertEqual([link.WorkerID for link in links], [1, 2])
        self.assertTrue(all(not link.CanExecute and link.MaxDailyQuantity is None for link in links))
        # 一度設定した担当可否と日上限は、同じ工程の更新でも変更しない。
        links[0].CanExecute = True
        links[0].MaxDailyQuantity = 25
        self.db.commit()
        self.assertEqual(self.call("PATCH", f"/product-processes/{process_id}", {"processName": "更新後"})[0], 200)
        self.db.refresh(links[0])
        self.assertTrue(links[0].CanExecute)
        self.assertEqual(links[0].MaxDailyQuantity, 25)
        # 不足リンクの作成を再実行しても、同じ組合せを重複登録しない。
        from app.services.worker_process_service import add_worker_skill_maps
        self.assertEqual(add_worker_skill_maps(self.db, self.db.get(ProductProcess, process_id)), [])
        self.assertEqual(len(self.db.scalars(select(WorkerSkillMap).where(
            WorkerSkillMap.ProductProcessID == process_id,
        )).all()), 2)
        # 未使用工程の削除では関連リンクも削除し、作業者本人は残す。
        self.assertEqual(self.call("DELETE", f"/product-processes/{process_id}")[0], 204)
        self.assertIsNone(self.db.scalar(select(WorkerSkillMap.WorkerSkillMapID).where(
            WorkerSkillMap.ProductProcessID == process_id,
        )))
        self.assertIsNotNone(self.db.get(Worker, 1))

    # 設備候補の所属拠点、片方指定、時間の範囲をサーバーでも確認する。
    def test_process_resource_api_checks_scope_and_duration(self):
        self.db.add_all([
            Resource(ResourceID=1, LocationID=1, ResourceName="同じ拠点"),
            Resource(ResourceID=2, LocationID=2, ResourceName="別拠点"),
            ResourceGroup(ResourceGroupID=1, LocationID=1, GroupName="設備群"),
        ])
        self.db.commit()
        # 有効な候補。既定値で補う他の時間は0にする。
        body = {"productProcessId": 1, "resourceId": 1, "fixedMinutes": 5}
        status, candidate = self.call("POST", "/product-process-resources", body)
        self.assertEqual(status, 201, candidate)
        self.assertEqual(candidate["productProcessId"], 1)
        for invalid in ({"resourceId": 2}, {"resourceId": None}, {"resourceGroupId": 1},
                        {"fixedMinutes": -1}, {"fixedMinutes": None}, {"fixedMinutes": 0},
                        {"minutesPerUnit": 0.00001}, {"minutesPerUnit": 100000000}):
            with self.subTest(invalid=invalid):
                self.assertEqual(self.call("POST", "/product-process-resources", {**body, **invalid})[0], 422)

    # 登録順と異なる工程番号順で生成し、候補・時間・待ち時間を維持して属性なしにする。
    def test_product_process_generation_preserves_execution_data(self):
        # 既存の工程を後続にし、後から登録する工程を先行にする。
        self.db.get(ProductProcess, 1).SequenceNumber = 2
        self.db.add(Resource(ResourceID=1, LocationID=1, ResourceName="設備"))
        self.db.add(ResourceGroup(ResourceGroupID=1, LocationID=1, GroupName="設備群"))
        self.db.add(ProductProcess(ProductProcessID=2, ProductID=1, SequenceNumber=1, ProcessName="準備", MinLagAfterMin=3, MaxLagAfterMin=9))
        self.db.flush()
        self.db.add_all([
            ProductProcessResource(ProductProcessID=2, ResourceID=1, SetupMinutes=2, FixedMinutes=3, MinutesPerUnit=0.125, Priority=2),
            ProductProcessResource(ProductProcessID=1, ResourceGroupID=1, FixedMinutes=7),
        ])
        self.db.commit()
        # オーダー属性の保存列がなくても、数量を用いたタスク生成を行う。
        order = self.create(quantity=3)
        status, tasks = self.call("POST", f'/orders/{order["orderId"]}/generate-tasks')
        self.assertEqual(status, 200, tasks)
        self.assertEqual([task["productProcessId"] for task in tasks], [2, 1])
        self.assertEqual([task["taskNo"] for task in tasks], ["1", "2"])
        self.assertEqual([task["taskName"] for task in tasks], ["準備", "製造"])
        self.assertEqual(tasks[0]["options"][0]["durationMin"], 6)
        self.assertEqual(tasks[0]["options"][0]["priority"], 2)
        self.assertEqual(tasks[1]["options"][0]["resourceGroupId"], 1)
        self.assertEqual(tasks[1]["options"][0]["durationMin"], 7)
        self.assertTrue(all(task["attributesJSON"] is None for task in tasks))
        # 先行工程に指定した待ち時間が、生成された前後関係へ移る。
        status, dependencies = self.call("GET", f'/orders/{order["orderId"]}/dependencies')
        self.assertEqual(status, 200, dependencies)
        self.assertEqual(len(dependencies), 1)
        self.assertEqual((dependencies[0]["lagMin"], dependencies[0]["maxLagMin"]), (3, 9))
        # 工程編集後の再生成でも、以前取得した工程一覧を使い回さない。
        self.assertEqual(self.call("PATCH", "/product-processes/2", {"processName": "準備変更"})[0], 200)
        self.assertEqual(self.call("POST", f'/orders/{order["orderId"]}/generate-tasks?replace=true')[1][0]["taskName"], "準備変更")

    # 製品未指定・工程未登録で生成を拒否し、入力不備の再生成で既存タスクを失わない。
    def test_generation_requires_product_processes_and_preserves_existing_tasks(self):
        # 製品未指定のオーダー自体は登録できるが、タスクは生成しない。
        no_product = self.create(wbsNumber="NO-PRODUCT", productId=None)
        self.assertEqual(self.call("POST", f'/orders/{no_product["orderId"]}/generate-tasks')[0], 422)
        no_process = self.create(wbsNumber="NO-PROCESS", locationId=2, productId=2)
        self.assertEqual(self.call("POST", f'/orders/{no_process["orderId"]}/generate-tasks')[0], 422)
        # 登録後に製品が無効になった場合も、生成済みタスクを保持する。
        order = self.create()
        status, tasks = self.call("POST", f'/orders/{order["orderId"]}/generate-tasks')
        self.assertEqual(status, 200, tasks)
        self.db.get(Product, 1).DeleteFlag = True
        self.db.commit()
        self.assertEqual(self.call("POST", f'/orders/{order["orderId"]}/generate-tasks?replace=true')[0], 422)
        self.assertIsNotNone(self.db.get(Task, tasks[0]["taskId"]))

    # 離れた番号の交換でも、既存タスクと設備候補の工程IDは変えない。
    def test_process_number_swap_preserves_references(self):
        # 二番目・三番目の工程と、別製品に属する工程。
        second = self.call("POST", "/product-processes", {"productId": 1, "sequenceNumber": 2, "processName": "第二"})[1]
        third = self.call("POST", "/product-processes", {"productId": 1, "sequenceNumber": 3, "processName": "第三"})[1]
        other = self.call("POST", "/product-processes", {"productId": 2, "sequenceNumber": 1, "processName": "別製品"})[1]
        self.db.add(Resource(ResourceID=1, LocationID=1, ResourceName="設備"))
        self.db.flush()
        self.db.add(ProductProcessResource(ProductProcessID=1, ResourceID=1, FixedMinutes=5))
        self.db.commit()
        # 生成済みタスクは工程マスタの並べ替えで書き換えない。
        order = self.create()
        tasks = self.call("POST", f'/orders/{order["orderId"]}/generate-tasks')[1]
        self.assertEqual(self.call("PATCH", "/product-processes/1", {"sequenceNumber": 3})[0], 200)
        rows = self.call("GET", "/product-processes?productId=1")[1]
        self.assertEqual([row["productProcessId"] for row in rows], [third["productProcessId"], second["productProcessId"], 1])
        self.assertEqual([row["sequenceNumber"] for row in rows], [1, 2, 3])
        self.assertEqual(self.db.get(ProductProcess, other["productProcessId"]).SequenceNumber, 1)
        self.assertEqual(self.db.scalar(select(ProductProcessResource.ProductProcessID)), 1)
        self.assertEqual(self.call("GET", f'/orders/{order["orderId"]}/tasks')[1], tasks)
        # 隣の番号へ戻す操作は、上下ボタンと同じ一つ分の交換になる。
        self.assertEqual(self.call("PATCH", "/product-processes/1", {"sequenceNumber": 2})[0], 200)
        self.assertEqual([row["productProcessId"] for row in self.call("GET", "/product-processes?productId=1")[1]],
                         [third["productProcessId"], 1, second["productProcessId"]])
        self.assertEqual(self.call("DELETE", "/product-processes/1")[0], 409)

    # 新規挿入と削除で番号が欠けず、範囲外の指定では元の順番を保つ。
    def test_process_insert_delete_and_invalid_order(self):
        # 先頭へ挿入すると、もとの工程は二番目へ移る。
        first = self.call("POST", "/product-processes", {"productId": 1, "sequenceNumber": 1, "processName": "先頭"})[1]
        middle = self.call("POST", "/product-processes", {"productId": 1, "sequenceNumber": 2, "processName": "中間"})[1]
        rows = self.call("GET", "/product-processes?productId=1")[1]
        self.assertEqual([row["productProcessId"] for row in rows], [first["productProcessId"], middle["productProcessId"], 1])
        for number in (0, 4, -1):
            self.assertEqual(self.call("PATCH", "/product-processes/1", {"sequenceNumber": number})[0], 422)
            self.assertEqual(self.call("GET", "/product-processes?productId=1")[1], rows)
        self.assertEqual(self.call("POST", "/product-processes", {"productId": 1, "sequenceNumber": 5, "processName": "範囲外"})[0], 422)
        self.assertEqual(self.call("DELETE", f'/product-processes/{middle["productProcessId"]}')[0], 204)
        self.assertEqual([row["sequenceNumber"] for row in self.call("GET", "/product-processes?productId=1")[1]], [1, 2])
        # 先頭・末尾を削除した後は、最初の工程番号1を再び登録できる。
        self.assertEqual(self.call("DELETE", f'/product-processes/{first["productProcessId"]}')[0], 204)
        self.assertEqual(self.call("DELETE", "/product-processes/1")[0], 204)
        self.assertEqual(self.call("POST", "/product-processes", {"productId": 1, "sequenceNumber": 1, "processName": "再登録"})[0], 201)

    # 以前の10・20の工程番号も、番号交換の保存時に1・2へ揃える。
    def test_legacy_process_numbers_become_contiguous_on_save(self):
        self.db.get(ProductProcess, 1).SequenceNumber = 10
        self.db.add(ProductProcess(ProductID=1, SequenceNumber=20, ProcessName="旧番号"))
        self.db.commit()
        self.assertEqual(self.call("PATCH", "/product-processes/1", {"sequenceNumber": 2})[0], 200)
        rows = self.call("GET", "/product-processes?productId=1")[1]
        self.assertEqual([row["sequenceNumber"] for row in rows], [1, 2])
        self.assertEqual(rows[1]["productProcessId"], 1)

    # 実績登録済みや開始済みのタスクを、再生成で削除しないことを確認する。
    def test_regeneration_protects_started_and_actual_tasks(self):
        # 作業を開始した生成済みタスク。
        order = self.create()
        status, tasks = self.call("POST", f'/orders/{order["orderId"]}/generate-tasks')
        self.assertEqual(status, 200, tasks)
        task = self.db.get(Task, tasks[0]["taskId"])
        task.Status = "IN_PROGRESS"
        self.db.commit()
        self.assertEqual(self.call("POST", f'/orders/{order["orderId"]}/generate-tasks?replace=true')[0], 409)
        task.Status = "NOT_STARTED"
        self.db.add(WorkActual(TaskID=task.TaskID, Status="DONE", StartAt=datetime(2026, 10, 30, 6), EndAt=datetime(2026, 10, 30, 7)))
        self.db.commit()
        self.assertEqual(self.call("POST", f'/orders/{order["orderId"]}/generate-tasks?replace=true')[0], 409)
        self.assertIsNotNone(self.db.get(Task, task.TaskID))


# 拠点共通の曜日別勤務・停止例外・代表行削除を、実際のAPI受付処理で確認する。
class CalendarCrudTest(InMemoryApiTestCase):
    # 月曜午前の勤務を基本にし、曜日・時間帯・拠点を必要なテストだけ変更する。
    def create_work(self, **values):
        # APIへ送信する勤務1行の内容。
        body = {"locationId": 1, "dayOfWeek": 1, "startTime": "09:00:00", "endTime": "12:00:00",
                "workName": "午前", **values}
        status, work = self.call("POST", "/calendars", body)
        self.assertEqual(status, 201, work)
        return work

    # 指定勤務行へ月曜の停止例外を登録し、拠点共通への適用を確認する。
    def create_stop(self, calendar_id, **values):
        # 時差付きの日本時間を入力し、日本時間保存・出力を確認できる停止内容。
        body = {"calendarId": calendar_id, "startAt": "2026-11-09T10:00:00+09:00",
                 "endAt": "2026-11-09T11:00:00+09:00", "reason": "設備点検", **values}
        status, stop = self.call("POST", "/calendar-exceptions", body)
        self.assertEqual(status, 201, stop)
        return stop

    # 日本時間の月曜1日分を基本に、稼働区間をAPIから取得する。
    def working(self, calendar_id, start="2026-11-09T00:00:00+09:00", end="2026-11-10T00:00:00+09:00"):
        status, intervals = self.call("GET", f"/calendars/{calendar_id}/working-time?from={start}&to={end}")
        self.assertEqual(status, 200, intervals)
        return intervals

    # 曜日・午前午後をまとめて計算し、昼休み・削除済み勤務・別拠点を混ぜない。
    def test_weekly_rows_are_shared_and_lunch_other_locations_are_excluded(self):
        # 同じ拠点の月曜午前・午後と火曜勤務、別拠点の昼休み相当の勤務。
        morning = self.create_work()
        afternoon = self.create_work(startTime="13:00:00", endTime="18:00:00", workName="午後")
        tuesday = self.create_work(dayOfWeek=2, startTime="10:00:00", endTime="11:00:00", workName="火曜")
        self.create_work(locationId=2, startTime="12:00:00", endTime="13:00:00", workName="別拠点")
        # 削除済みの行が残っていても、昼休みを埋める勤務として使わない。
        removed = self.create_work(startTime="12:00:00", endTime="13:00:00", workName="削除対象")
        self.assertEqual(self.call("DELETE", f'/calendars/{removed["calendarId"]}')[0], 204)
        # いずれの有効勤務行IDでも、同じ拠点全体の結果を返す。
        expected = [
            {"start": "2026-11-09T09:00:00+09:00", "end": "2026-11-09T12:00:00+09:00"},
            {"start": "2026-11-09T13:00:00+09:00", "end": "2026-11-09T18:00:00+09:00"},
            {"start": "2026-11-10T10:00:00+09:00", "end": "2026-11-10T11:00:00+09:00"},
        ]
        for work in (morning, afternoon, tuesday):
            with self.subTest(calendar_id=work["calendarId"]):
                self.assertEqual(self.working(work["calendarId"], end="2026-11-11T00:00:00+09:00"), expected)
        status, rows = self.call("GET", "/calendars?locationId=1")
        self.assertEqual(status, 200, rows)
        self.assertEqual({row["calendarId"] for row in rows}, {morning["calendarId"], afternoon["calendarId"], tuesday["calendarId"]})
        self.assertEqual(self.call("GET", "/locations/1")[1]["calendarId"], morning["calendarId"])

    # 同日勤務を確認期間で切り取り、翌日の期間へ勤務を持ち越さない。
    def test_same_day_work_clips_range_without_previous_day_work(self):
        # 月曜午前の勤務。確認期間の開始・終了で両端を切り取る。
        morning = self.create_work()
        self.assertEqual(self.working(morning["calendarId"], start="2026-11-09T10:00:00+09:00", end="2026-11-09T11:00:00+09:00"), [
            {"start": "2026-11-09T10:00:00+09:00", "end": "2026-11-09T11:00:00+09:00"},
        ])
        self.assertEqual(self.working(morning["calendarId"], start="2026-11-10T00:00:00+09:00", end="2026-11-10T08:00:00+09:00"), [])

    # 旧DBに残る不正勤務を、対象IDを示して計算読込時に拒否する。
    def test_legacy_overnight_work_is_rejected_before_expansion(self):
        from datetime import time
        from types import SimpleNamespace
        from unittest.mock import Mock
        from fastapi import HTTPException
        from app.services.calendar_service import calendar_specs

        # 新しいDB制約で保存できない旧勤務行を、読込結果として再現する。
        legacy = SimpleNamespace(CalendarID=123, LocationID=1, DeleteFlag=False,
                                 StartTime=time(22), EndTime=time(6))
        # DBへ接続せず、既存勤務が返された状況を用意する。
        db = Mock()
        db.get.return_value = legacy
        db.scalars.return_value.all.return_value = [legacy]
        with self.assertRaises(HTTPException) as caught:
            calendar_specs(db, legacy.CalendarID)
        self.assertEqual(caught.exception.status_code, 422)
        self.assertIn("勤務行 123", caught.exception.detail)

    # 複数勤務行の例外を拠点単位で取得し、日本時間で保存後に停止としてだけ適用する。
    def test_stops_on_different_rows_are_shared_and_use_jst(self):
        # 午前・午後と、影響が混ざらないことを確認する別拠点の勤務。
        morning = self.create_work()
        afternoon = self.create_work(startTime="13:00:00", endTime="18:00:00", workName="午後")
        other = self.create_work(locationId=2)
        # 午後行へ登録した午前停止も、午前行へ登録した午後停止も拠点全体へ適用する。
        first = self.create_stop(afternoon["calendarId"])
        second = self.create_stop(morning["calendarId"], startAt="2026-11-09T14:00:00+09:00", endAt="2026-11-09T15:00:00+09:00")
        outside = self.create_stop(morning["calendarId"], startAt="2026-11-08T20:00:00+09:00", endAt="2026-11-08T21:00:00+09:00")
        self.create_stop(other["calendarId"], startAt="2026-11-09T09:00:00+09:00", endAt="2026-11-09T18:00:00+09:00")
        self.assertEqual(first["startAt"], "2026-11-09T10:00:00+09:00")
        self.assertEqual(first["endAt"], "2026-11-09T11:00:00+09:00")
        self.assertEqual(self.db.get(CalendarException, first["exceptionId"]).StartAt, datetime(2026, 11, 9, 10))
        for key in ("startTime", "endTime", "isWorking"):
            self.assertNotIn(key, first)
        status, stops = self.call("GET", "/calendar-exceptions?locationId=1")
        self.assertEqual(status, 200, stops)
        self.assertEqual({row["exceptionId"] for row in stops}, {first["exceptionId"], second["exceptionId"], outside["exceptionId"]})
        self.assertEqual(len(self.call("GET", "/calendar-exceptions?locationId=2")[1]), 1)
        self.assertEqual(len(self.call("GET", f'/calendar-exceptions?calendarId={afternoon["calendarId"]}')[1]), 1)
        # 勤務時間外の例外は稼働を追加せず、昼休みもそのまま残す。
        expected = [
            {"start": "2026-11-09T09:00:00+09:00", "end": "2026-11-09T10:00:00+09:00"},
            {"start": "2026-11-09T11:00:00+09:00", "end": "2026-11-09T12:00:00+09:00"},
            {"start": "2026-11-09T13:00:00+09:00", "end": "2026-11-09T14:00:00+09:00"},
            {"start": "2026-11-09T15:00:00+09:00", "end": "2026-11-09T18:00:00+09:00"},
        ]
        self.assertEqual(self.working(morning["calendarId"]), expected)
        self.assertEqual(self.working(afternoon["calendarId"]), expected)

    # 代表勤務行を削除しても、設備の所属を維持し、拠点・停止例外は残行へ引き継ぐ。
    def test_deleting_representative_reassigns_all_references(self):
        first = self.create_work()
        replacement = self.create_work(startTime="13:00:00", endTime="18:00:00", workName="午後")
        other = self.create_work(locationId=2)
        # 有効な設備と、履歴のために残る削除済み設備は拠点だけを参照する。
        self.db.add_all([
            Resource(ResourceID=1, LocationID=1, ResourceName="設備"),
            Resource(ResourceID=2, LocationID=1, ResourceName="削除済み設備", DeleteFlag=True),
        ])
        self.db.commit()
        stop = self.create_stop(first["calendarId"])
        self.assertEqual(self.call("DELETE", f'/calendars/{first["calendarId"]}')[0], 204)
        self.assertEqual(self.db.get(Location, 1).CalendarID, replacement["calendarId"])
        for resource_id in (1, 2):
            self.assertEqual(self.db.get(Resource, resource_id).LocationID, 1)
        status, saved_stop = self.call("GET", f'/calendar-exceptions/{stop["exceptionId"]}')
        self.assertEqual(status, 200, saved_stop)
        self.assertEqual(saved_stop["calendarId"], replacement["calendarId"])
        for key in ("reason", "startAt", "endAt", "createdAt"):
            self.assertEqual(saved_stop[key], stop[key])
        self.assertTrue(self.db.get(Calendar, first["calendarId"]).DeleteFlag)
        self.assertEqual(self.call("GET", f'/calendars/{first["calendarId"]}')[0], 404)
        self.assertEqual(self.db.get(Location, 2).CalendarID, other["calendarId"])
        self.assertFalse(self.db.get(Calendar, other["calendarId"]).DeleteFlag)

    # 最終行に停止例外がある間は変更を取り消し、例外削除後は参照をnullに戻す。
    def test_last_row_requires_stops_removed_and_clears_references(self):
        work = self.create_work()
        self.db.add(Resource(ResourceID=1, LocationID=1, ResourceName="設備"))
        self.db.commit()
        stop = self.create_stop(work["calendarId"])
        self.assertEqual(self.call("DELETE", f'/calendars/{work["calendarId"]}')[0], 409)
        self.assertFalse(self.db.get(Calendar, work["calendarId"]).DeleteFlag)
        self.assertEqual(self.db.get(Location, 1).CalendarID, work["calendarId"])
        self.assertEqual(self.db.get(Resource, 1).LocationID, 1)
        self.assertEqual(self.call("GET", f'/calendar-exceptions/{stop["exceptionId"]}')[0], 200)
        self.assertEqual(self.call("DELETE", f'/calendar-exceptions/{stop["exceptionId"]}')[0], 204)
        self.assertEqual(self.call("DELETE", f'/calendars/{work["calendarId"]}')[0], 204)
        self.assertIsNone(self.db.get(Location, 1).CalendarID)
        self.assertEqual(self.db.get(Resource, 1).LocationID, 1)
        self.assertTrue(self.db.get(Calendar, work["calendarId"]).DeleteFlag)
        self.assertEqual(self.call("GET", "/calendars?locationId=1")[1], [])

    # 日曜0・土曜6を受理し、登録した曜日だけが勤務時間になることを確認する。
    def test_sunday_zero_and_saturday_six(self):
        sunday = self.create_work(dayOfWeek=0, workName="日曜勤務")
        saturday = self.create_work(dayOfWeek=6, workName="土曜勤務")
        self.assertEqual(self.working(sunday["calendarId"], start="2026-11-08T00:00:00+09:00", end="2026-11-09T00:00:00+09:00"), [
            {"start": "2026-11-08T09:00:00+09:00", "end": "2026-11-08T12:00:00+09:00"},
        ])
        self.assertEqual(self.working(saturday["calendarId"], start="2026-11-14T00:00:00+09:00", end="2026-11-15T00:00:00+09:00"), [
            {"start": "2026-11-14T09:00:00+09:00", "end": "2026-11-14T12:00:00+09:00"},
        ])
        self.assertEqual(self.working(sunday["calendarId"]), [])

    # 許可曜日ルールも同じ番号を使い、日曜の表示名がずれないことを確認する。
    def test_allowed_weekdays_share_sunday_zero(self):
        from datetime import timedelta
        from app.core.timeutil import weekday_number
        from app.engine.problem import Problem, PRule, PTask
        from app.engine.rules.allowed_weekdays import AllowedWeekdays, blocked_ranges
        from app.engine.result import SAssignment
        # 日曜から1週間を用意し、0～6が暦と一致することを確認する。
        start = datetime(2026, 11, 8)
        self.assertEqual([weekday_number(start + timedelta(days=i)) for i in range(7)], list(range(7)))
        problem = Problem(horizon_start=start, horizon=7 * 1440, tz="Asia/Tokyo", resources={},
                          tasks={1: PTask(id=1, order_id=1, name="作業", attrs={}, options=[])}, orders={})
        self.assertEqual(blocked_ranges(problem, [0]), [(i * 1440, (i + 1) * 1440) for i in range(1, 7)])
        rule = PRule(id=1, type_key="allowed_weekdays", name="日曜のみ", selector={}, params={"weekdays": [0]})
        issues = AllowedWeekdays().check(problem, rule, [SAssignment(task_id=1, resource_id=1, start=1440, end=1500)])
        self.assertEqual(len(issues), 1)
        self.assertIn("日 のみ実行可能", issues[0].message)
        self.assertEqual(AllowedWeekdays().params_schema["properties"]["weekdays"]["items"],
                         {"type": "integer", "minimum": 0, "maximum": 6})

    # 無効な曜日・時刻・拠点は422で拒否し、勤務行を保存しない。
    def test_invalid_work_values_are_rejected(self):
        # DB制約エラーへ進む前に、APIで入力を拒否すべき値。
        body = {"locationId": 1, "dayOfWeek": 1, "startTime": "09:00:00", "endTime": "12:00:00"}
        for values in ({"dayOfWeek": -1}, {"dayOfWeek": 7}, {"dayOfWeek": 8}, {"dayOfWeek": None}, {"startTime": None},
                       {"endTime": "25:00:00"}, {"startTime": "09:00:00+09:00"},
                       {"startTime": "22:00:00", "endTime": "06:00:00"}, {"endTime": "09:00:00"},
                       {"endTime": "08:00:00"}, {"locationId": 999},
                       {"deleteFlag": True}, {"workName": "x" * 51}):
            with self.subTest(values=values):
                status, result = self.call("POST", "/calendars", {**body, **values})
                self.assertEqual(status, 422, result)
                self.assertIsNone(self.db.scalar(select(Calendar.CalendarID)))

    # 例外の逆転・同時刻・無効参照と、部分更新時の不正な組合せを拒否する。
    def test_invalid_stops_and_partial_updates_preserve_original_values(self):
        work = self.create_work()
        stop = self.create_stop(work["calendarId"])
        # 部分更新でも、送信されない開始日時を既存値で補って順序を確認する。
        for values in ({"endAt": "2026-11-09T09:59:00+09:00"}, {"endAt": "2026-11-09T10:00:00+09:00"},
                       {"startAt": None}, {"calendarId": 999}):
            with self.subTest(values=values):
                self.assertEqual(self.call("PATCH", f'/calendar-exceptions/{stop["exceptionId"]}', values)[0], 422)
                self.assertEqual(self.call("GET", f'/calendar-exceptions/{stop["exceptionId"]}')[1], stop)
        # 勤務の部分更新でも既存値と組み合わせ、逆転・同時刻・夜勤を拒否する。
        for values in ({"dayOfWeek": 7}, {"endTime": "09:00:00"}, {"endTime": "08:00:00"},
                       {"startTime": "12:00:00"}, {"startTime": "13:00:00"},
                       {"startTime": "22:00:00", "endTime": "06:00:00"}):
            with self.subTest(values=values):
                self.assertEqual(self.call("PATCH", f'/calendars/{work["calendarId"]}', values)[0], 422)
                self.assertEqual(self.call("GET", f'/calendars/{work["calendarId"]}')[1], work)
        status, updated = self.call("PATCH", f'/calendars/{work["calendarId"]}', {"workName": "勤務名変更"})
        self.assertEqual(status, 200, updated)
        self.assertEqual(updated["workName"], "勤務名変更")
        self.assertEqual(updated["updatedBy"], "order-test")
        for key in ("dayOfWeek", "startTime", "endTime", "createdAt"):
            self.assertEqual(updated[key], work[key])
        self.assertEqual(self.call("GET", "/calendar-exceptions?locationId=invalid")[0], 422)

    # 拠点・設備・勤務行・停止例外の所属が、他拠点へ変更されないことを確認する。
    def test_cross_location_calendar_references_are_rejected(self):
        first = self.create_work()
        other = self.create_work(locationId=2)
        stop = self.create_stop(first["calendarId"])
        # 拠点の代表解除と別拠点への差し替え、勤務行・例外の拠点移動を拒否する。
        for path, values in (("/locations/1", {"calendarId": other["calendarId"]}),
                             ("/locations/1", {"calendarId": None}),
                             (f'/calendars/{first["calendarId"]}', {"locationId": 2}),
                             (f'/calendar-exceptions/{stop["exceptionId"]}', {"calendarId": other["calendarId"]})):
            with self.subTest(path=path, values=values):
                self.assertEqual(self.call("PATCH", path, values)[0], 422)
        # 設備は有効な所属拠点を要求し、個別のカレンダー項目を持たない。
        self.assertEqual(self.call("POST", "/resources", {"locationId": 999, "resourceName": "無効拠点"})[0], 422)
        status, resource = self.call("POST", "/resources", {"locationId": 1, "resourceName": "設備"})
        self.assertEqual(status, 201, resource)
        self.assertEqual(self.call("PATCH", f'/resources/{resource["resourceId"]}', {"locationId": 999})[0], 422)
        self.assertEqual(self.call("GET", f'/resources/{resource["resourceId"]}')[1]["locationId"], 1)
        self.assertNotIn("calendarId", resource)
        self.assertNotIn("resourceType", resource)

    # 廃止したルートと組織・親カレンダー等の項目を公開しない。
    def test_removed_routes_and_columns_are_absent(self):
        work = self.create_work()
        for key in ("calendarName", "parentCalendarId", "patternId", "shiftName", "validFrom", "validTo"):
            self.assertNotIn(key, work)
        self.assertIn("workName", work)
        self.assertIn("updatedAt", work)
        self.assertIn("updatedBy", work)
        self.assertNotIn("organizationId", self.call("GET", "/locations/1")[1])
        for path in ("/organizations", "/calendar-patterns"):
            self.assertEqual(self.call("GET", path)[0], 404)


# 日本時間でのDB保存とAPI表現、日付境界を確認する。
class JapaneseTimeTest(InMemoryApiTestCase):
    # UTC入力も日本時間入力も同じ日本時間で保存し、小数秒を保持する。
    def test_offsets_and_fractional_seconds_are_saved_in_japan_time(self):
        from app.core.timeutil import to_jst_naive, as_jst
        from app.schemas.base import JstDatetime
        from pydantic import TypeAdapter
        adapter = TypeAdapter(JstDatetime)
        # UTCで前日15時は、日本時間では翌日0時になる。
        value = adapter.validate_python("2026-11-08T15:30:00.123456Z")
        self.assertEqual(value, datetime(2026, 11, 9, 0, 30, 0, 123456))
        self.assertEqual(adapter.dump_python(value, mode="json"), "2026-11-09T00:30:00.123456+09:00")
        self.assertEqual(to_jst_naive(value), value)
        self.assertEqual(as_jst(value).utcoffset().total_seconds(), 32400)
        # 時差なしの入力も、日本時間の値をそのまま保持する。
        self.assertEqual(adapter.validate_python("2026-11-09T00:30:00.123456"), value)

    # 日本時間の日付境界が、計画の分数計算や曜日判定でずれないことを確認する。
    def test_plan_days_and_stop_database_value_use_japan_time(self):
        from app.engine.problem import Problem
        problem = Problem(horizon_start=datetime(2026, 11, 9, 23), horizon=120,
                          tz="Asia/Tokyo", resources={}, tasks={}, orders={})
        self.assertEqual([(day.isoformat(), start, end) for day, start, end in problem.local_days()],
                         [("2026-11-09", 0, 60), ("2026-11-10", 60, 120)])
        status, work = self.call("POST", "/calendars", {
            "locationId": 1, "dayOfWeek": 1, "startTime": "09:00:00", "endTime": "18:00:00"})
        self.assertEqual(status, 201)
        status, stop = self.call("POST", "/calendar-exceptions", {
            "calendarId": work["calendarId"], "startAt": "2026-11-09T00:00:00Z",
            "endAt": "2026-11-09T01:00:00Z"})
        self.assertEqual(status, 201)
        self.assertEqual(stop["startAt"], "2026-11-09T09:00:00+09:00")
        self.assertEqual(self.db.get(CalendarException, stop["exceptionId"]).StartAt, datetime(2026, 11, 9, 9))
        # 登録履歴も日本時間を明示して返す。
        self.assertTrue(stop["createdAt"].endswith("+09:00"))


if __name__ == "__main__":
    unittest.main()

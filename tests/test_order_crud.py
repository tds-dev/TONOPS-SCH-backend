"""実DB・設定ファイル・外部通信を使わず、オーダーCRUDと既存データの保持を確認するテスト。"""
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
    from app.models.masters import Location, Organization, Product, ProductProcess, ProductProcessResource, CalculationSetting, Resource, ResourceGroup
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
               "scheme": "http", "path": route, "raw_path": route.encode(), "query_string": query.encode(),
               "headers": [(b"content-type", b"application/json")], "server": ("test", 80), "client": ("test", 1),
               "root_path": ""}, receive, send)
    # 分割された本文をまとめ、APIの返却値を読み取る。
    status = next(message["status"] for message in messages if message["type"] == "http.response.start")
    content = b"".join(message.get("body", b"") for message in messages if message["type"] == "http.response.body")
    return status, json.loads(content) if content else None


# 登録から削除までの実APIと、誤入力・既存計画への影響を確認する。
class OrderCrudTest(unittest.TestCase):
    # テストごとに独立したDBと最小限のマスタを準備する。
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
        self.db.add(Organization(OrganizationID=1, OrganizationName="組織"))
        self.db.flush()
        self.db.add_all([Location(LocationID=1, OrganizationID=1, LocationName="拠点A"),
                         Location(LocationID=2, OrganizationID=1, LocationName="拠点B")])
        self.db.flush()
        self.db.add_all([Product(ProductID=1, LocationID=1, ProductName="製品A"),
                         Product(ProductID=2, LocationID=2, ProductName="製品B")])
        self.db.flush()
        self.db.add(ProductProcess(ProductProcessID=1, ProductID=1, SequenceNumber=1, ProcessName="製造"))
        self.db.commit()

    # テスト用のDBを閉じ、次のテストへデータを持ち越さない。
    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    # APIへ通信を発生させずに問い合わせる共通処理。
    def call(self, method, path, body=None):
        return asyncio.run(request(self.app, method, "/api/v1" + path, body))

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
        self.assertEqual(order["releaseAt"], "2026-10-30T00:00:00Z")
        self.assertEqual(order["shippingDate"], "2026-10-30T06:00:00Z")
        # 廃止した親オーダーIDをAPIへ返さない。
        self.assertNotIn("parentOrderId", order)
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

    # 無効な値を保存せず、必須・範囲・所属・日時・選択値を確認する。
    def test_rejects_invalid_create(self):
        for values in ({"wbsNumber": "  "}, {"orderName": "x" * 201}, {"quantity": -1}, {"quantity": 0.0001},
                       {"quantity": 1e15}, {"priority": 0}, {"priority": None}, {"status": "UNKNOWN"},
                       {"orderType": None}, {"planOwner": "UNKNOWN"}, {"productId": 2},
                       {"locationId": 999}, {"attributesJSON": []},
                       {"releaseAt": "2026-10-30T12:00:00Z", "deadLine": "2026-10-30T11:00:00Z"}):
            with self.subTest(values=values):
                status, result = self.call("POST", "/orders", {"locationId": 1, "wbsNumber": "INVALID", "orderName": "依頼", **values})
                self.assertEqual(status, 422, result)
                self.assertIsNone(self.db.scalar(select(Order.OrderID)))

    # 既存値と変更値を合わせた日時の前後関係と、所属拠点変更を拒否する。
    def test_partial_update_uses_existing_values(self):
        order = self.create(releaseAt="2026-10-30T09:00:00Z", deadLine="2026-10-30T12:00:00Z")
        for values in ({"deadLine": "2026-10-30T08:00:00Z"}, {"locationId": 2}, {"orderName": None}):
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
                         Resource(ResourceID=1, LocationID=1, ResourceName="設備", ResourceType="MACHINE")])
        self.db.flush()
        self.db.add(Plan(PlanID=1, LocationID=1, PlanName="計画", CalculationSettingID=1,
                         HorizonStart=datetime(2026, 10, 30), HorizonEnd=datetime(2026, 10, 31)))
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
        self.db.add(WorkActual(TaskID=1, Status="DONE"))
        self.db.commit()
        self.assertEqual(self.call("PATCH", f"/orders/{order_id}", {"attributesJSON": {"family": "B"}})[0], 409)
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

    # 登録順と異なる工程番号順で生成し、候補・時間・待ち時間・オーダー属性を保持する。
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
        # 属性はオーダーから各タスクへ引き継ぐ。
        order = self.create(quantity=3, attributesJSON={"family": "A"})
        status, tasks = self.call("POST", f'/orders/{order["orderId"]}/generate-tasks')
        self.assertEqual(status, 200, tasks)
        self.assertEqual([task["productProcessId"] for task in tasks], [2, 1])
        self.assertEqual([task["taskNo"] for task in tasks], ["1", "2"])
        self.assertEqual([task["taskName"] for task in tasks], ["準備", "製造"])
        self.assertEqual(tasks[0]["options"][0]["durationMin"], 6)
        self.assertEqual(tasks[0]["options"][0]["priority"], 2)
        self.assertEqual(tasks[1]["options"][0]["resourceGroupId"], 1)
        self.assertEqual(tasks[1]["options"][0]["durationMin"], 7)
        self.assertTrue(all(task["attributesJSON"] == {"family": "A"} for task in tasks))
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
        self.db.add(WorkActual(TaskID=task.TaskID, Status="DONE"))
        self.db.commit()
        self.assertEqual(self.call("POST", f'/orders/{order["orderId"]}/generate-tasks?replace=true')[0], 409)
        self.assertIsNotNone(self.db.get(Task, task.TaskID))


if __name__ == "__main__":
    unittest.main()

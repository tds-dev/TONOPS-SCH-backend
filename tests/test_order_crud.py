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
    from app.models.masters import Location, Organization, Product, Routing, RoutingStep, PlanProfile, Resource
    from app.models.transactions import Actual, Order, Plan, PlanAssignment, Task
    from app.routers.crud import crud_router
    from app.routers.orders import routers


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
        self.app.include_router(crud_router(Product, "/products", "Products"), prefix="/api/v1")
        self.app.dependency_overrides[get_db] = lambda: self.db
        self.db.add(Organization(OrganizationID=1, OrganizationCode="ORG", OrganizationName="組織"))
        self.db.flush()
        self.db.add_all([Location(LocationID=1, OrganizationID=1, LocationCode="A", LocationName="拠点A"),
                         Location(LocationID=2, OrganizationID=1, LocationCode="B", LocationName="拠点B")])
        self.db.flush()
        self.db.add_all([Product(ProductID=1, LocationID=1, ProductCode="P1", ProductName="製品A"),
                         Product(ProductID=2, LocationID=2, ProductCode="P2", ProductName="製品B")])
        self.db.flush()
        self.db.add_all([Routing(RoutingID=1, ProductID=1, RoutingName="工程A"), Routing(RoutingID=2, ProductID=2, RoutingName="工程B")])
        self.db.flush()
        self.db.add(RoutingStep(RoutingID=1, StepNo=10, StepName="製造"))
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
        body = {"locationId": 1, "orderNo": "ORD-001", "orderName": "製造依頼", "productId": 1, **values}
        status, order = self.call("POST", "/orders", body)
        self.assertEqual(status, 201, order)
        return order

    # CRUD全体と、論理削除後に番号・タスク・親の情報が保持されることを確認する。
    def test_crud_preserves_unedited_data_and_tasks(self):
        parent = self.create(orderNo="PARENT")
        order = self.create(parentOrderId=parent["orderId"], routingId=1, quantity=12.345,
                            releaseAt="2026-10-30T09:00:00+09:00", dueAt="2026-10-30T12:00:00+09:00")
        order_id = order["orderId"]
        self.assertEqual(order["releaseAt"], "2026-10-30T00:00:00Z")
        self.assertEqual(order["priority"], 50)
        self.assertEqual(order["createdBy"], "order-test")
        self.assertEqual(self.call("GET", f"/orders/{order_id}")[0], 200)
        status, tasks = self.call("POST", f"/orders/{order_id}/generate-tasks")
        self.assertEqual(status, 200, tasks)
        self.assertEqual(len(tasks), 1)
        status, updated = self.call("PATCH", f"/orders/{order_id}", {"orderName": "変更後", "remarks": "備考"})
        self.assertEqual(status, 200, updated)
        for key in ("parentOrderId", "routingId", "quantity", "releaseAt", "dueAt", "createdAt"):
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
        for values in ({"orderNo": "  "}, {"orderName": "x" * 201}, {"quantity": -1}, {"quantity": 0.0001},
                       {"quantity": 1e15}, {"priority": 0}, {"priority": None}, {"status": "UNKNOWN"},
                       {"orderType": None}, {"planOwner": "UNKNOWN"}, {"productId": 2}, {"routingId": 2},
                       {"locationId": 999}, {"attributesJSON": []},
                       {"releaseAt": "2026-10-30T12:00:00Z", "dueAt": "2026-10-30T11:00:00Z"}):
            with self.subTest(values=values):
                status, result = self.call("POST", "/orders", {"locationId": 1, "orderNo": "INVALID", "orderName": "依頼", **values})
                self.assertEqual(status, 422, result)
                self.assertIsNone(self.db.scalar(select(Order.OrderID)))

    # 既存値と変更値を合わせた日時の前後関係と、所属拠点変更を拒否する。
    def test_partial_update_uses_existing_values(self):
        order = self.create(releaseAt="2026-10-30T09:00:00Z", dueAt="2026-10-30T12:00:00Z")
        for values in ({"dueAt": "2026-10-30T08:00:00Z"}, {"locationId": 2}, {"orderName": None}):
            with self.subTest(values=values):
                self.assertEqual(self.call("PATCH", f'/orders/{order["orderId"]}', values)[0], 422)
        self.assertEqual(self.call("PATCH", f'/orders/{order["orderId"]}', {"dueAt": None})[0], 200)

    # 削除済み番号も重複扱いとし、DBの不明瞭な制約エラーを避ける。
    def test_duplicate_numbers_include_deleted_orders(self):
        order = self.create()
        self.assertEqual(self.call("DELETE", f'/orders/{order["orderId"]}')[0], 204)
        self.assertEqual(self.call("POST", "/orders", {"locationId": 1, "orderNo": "ORD-001", "orderName": "重複"})[0], 409)
        self.assertEqual(self.create(locationId=2, productId=2)["locationId"], 2)

    # 計画に割付済みのタスクがある場合も、名称編集・履歴を残す削除は維持する。
    def test_planned_tasks_are_protected_and_history_survives_delete(self):
        order = self.create(quantity=10.123)
        order_id = order["orderId"]
        status, tasks = self.call("POST", f"/orders/{order_id}/generate-tasks")
        self.assertEqual(status, 200, tasks)
        self.db.add_all([PlanProfile(ProfileID=1, LocationID=1, ProfileName="標準"),
                         Resource(ResourceID=1, LocationID=1, ResourceCode="R1", ResourceName="設備", ResourceType="MACHINE")])
        self.db.flush()
        self.db.add(Plan(PlanID=1, LocationID=1, PlanNo="PLAN", PlanName="計画", ProfileID=1,
                         HorizonStart=datetime(2026, 10, 30), HorizonEnd=datetime(2026, 10, 31)))
        self.db.flush()
        self.db.add(PlanAssignment(PlanID=1, TaskID=tasks[0]["taskId"], ResourceID=1,
                                   StartAt=datetime(2026, 10, 30, 9), EndAt=datetime(2026, 10, 30, 10)))
        self.db.commit()
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
        self.db.add(Actual(TaskID=1, Status="DONE"))
        self.db.commit()
        self.assertEqual(self.call("PATCH", f"/orders/{order_id}", {"attributesJSON": {"family": "B"}})[0], 409)
        self.assertEqual(self.call("DELETE", f"/orders/{order_id}")[0], 204)
        self.assertIsNotNone(self.db.scalar(select(Actual.ActualID)))
        self.assertIsNotNone(self.db.get(Task, 1))

    # 未割付のタスクは、既存の再生成操作で変更した数量を反映できる。
    def test_unplanned_order_can_update_and_regenerate(self):
        order = self.create(quantity=10)
        order_id = order["orderId"]
        self.assertEqual(self.call("POST", f"/orders/{order_id}/generate-tasks")[0], 200)
        self.assertEqual(self.call("PATCH", f"/orders/{order_id}", {"quantity": 20})[0], 200)
        self.assertEqual(self.call("POST", f"/orders/{order_id}/generate-tasks?replace=true")[0], 200)
        self.assertEqual(self.call("GET", f"/orders/{order_id}/dependencies")[0], 200)

    # オーダー向け検証を指定していない既存マスタのCRUDが変わらないことを確認する。
    def test_other_crud_keeps_existing_behavior(self):
        status, product = self.call("POST", "/products", {"locationId": 1, "productCode": "NEW", "productName": "新製品"})
        self.assertEqual(status, 201, product)
        self.assertEqual(self.call("PATCH", f'/products/{product["productId"]}', {"productName": "更新"})[0], 200)
        self.assertEqual(self.call("DELETE", f'/products/{product["productId"]}')[0], 204)

    # 既存の製品・ルートが削除済みでも、参照を変えない名称編集は妨げない。
    def test_deleted_master_references_are_preserved(self):
        order = self.create(routingId=1)
        self.db.get(Product, 1).DeleteFlag = True
        self.db.get(Routing, 1).DeleteFlag = True
        self.db.commit()
        status, updated = self.call("PATCH", f'/orders/{order["orderId"]}', {"orderName": "参照を保持"})
        self.assertEqual(status, 200, updated)
        self.assertEqual(updated["productId"], 1)
        self.assertEqual(updated["routingId"], 1)
        self.assertEqual(self.call("POST", "/orders", {"locationId": 1, "orderNo": "NEW", "orderName": "無効参照", "productId": 1})[0], 422)


if __name__ == "__main__":
    unittest.main()

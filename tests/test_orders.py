"""Order系へ変更後のDB構造を前提に、オーダーAPIと関連機能を確認する回帰テスト。"""
import asyncio
from datetime import datetime
import json
import unittest
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from sqlalchemy import select, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.db import Base, get_db, make_engine
from app.engine.result import SAssignment
from app.engine.snapshot import build_problem
from app.engine.solve import write_results
from app.main import app
from app.models.masters import AttributeDefinition
from app.models.transactions import Order, Plan, PlanViolation, Task
from app.services.demo_seed import seed_demo


# HTTP通信や追加のクライアントライブラリを使わず、アプリへリクエストを渡す。
async def request_json(method, url, body=None):
    parts = urlsplit(url)
    payload = json.dumps(body).encode() if body is not None else b''
    messages = []

    # リクエスト本文をアプリへ渡す。
    async def receive():
        return {'type': 'http.request', 'body': payload, 'more_body': False}

    # アプリの返答をメモリ上に集める。
    async def send(message):
        messages.append(message)

    scope = {
        'type': 'http', 'asgi': {'version': '3.0'}, 'http_version': '1.1',
        'method': method, 'scheme': 'http', 'path': parts.path,
        'raw_path': parts.path.encode(), 'query_string': parts.query.encode(),
        'root_path': '', 'headers': [(b'content-type', b'application/json')],
        'client': ('test', 123), 'server': ('test', 80),
    }
    await app(scope, receive, send)
    status = next(message['status'] for message in messages if message['type'] == 'http.response.start')
    content = b''.join(message.get('body', b'') for message in messages if message['type'] == 'http.response.body')
    return status, json.loads(content) if content else None


class OrdersTest(unittest.TestCase):
    """テスト専用のメモリDBで、実DBを変更せずにOrder系の読書きを確認する。"""

    def setUp(self):
        # 毎回独立したDBを作り、デモの工程ルートとオーダーを用意する。
        self.engine = make_engine('sqlite://', poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine, expire_on_commit=False)
        self.seeded = seed_demo(self.db, now=datetime(2026, 10, 26, 10, tzinfo=ZoneInfo('Asia/Tokyo')))
        app.dependency_overrides[get_db] = lambda: self.db

    def tearDown(self):
        # テストの接続と画面用の依存関係を元に戻す。
        app.dependency_overrides.clear()
        self.db.close()
        self.engine.dispose()

    def request(self, method, url, body=None):
        # API呼出しを同期テストから実行する。
        return asyncio.run(request_json(method, url, body))

    def test_orders_crud_uses_order_table_and_columns(self):
        # 登録・検索・更新・削除が変更後のテーブル・列を通じて実行できることを確認する。
        status, order = self.request('POST', '/api/v1/orders', {
            'siteId': self.seeded['siteId'], 'orderNo': 'OR-TEST', 'orderName': '改称テスト',
        })
        self.assertEqual(status, 201, order)
        self.assertNotIn('jobId', order)
        order_id = order['orderId']
        self.assertEqual(order['orderType'], 'ORDER')
        self.assertNotIn('orderKind', order)
        stored = self.db.execute(text('SELECT OrderNo, OrderName FROM T_Orders WHERE OrderID = :id'), {'id': order_id}).one()
        self.assertEqual(tuple(stored), ('OR-TEST', '改称テスト'))
        status, rows = self.request('GET', f'/api/v1/orders?orderId={order_id}')
        self.assertEqual(status, 200)
        self.assertEqual([row['orderId'] for row in rows], [order_id])
        status, updated = self.request('PATCH', f'/api/v1/orders/{order_id}', {'orderName': '更新後', 'orderType': 'PROJECT'})
        self.assertEqual(status, 200)
        self.assertEqual(updated['orderName'], '更新後')
        self.assertEqual(updated['orderType'], 'PROJECT')
        self.assertEqual(self.db.execute(text('SELECT OrderType FROM T_Orders WHERE OrderID = :id'), {'id': order_id}).scalar_one(), 'PROJECT')
        self.assertEqual(self.request('DELETE', f'/api/v1/orders/{order_id}')[0], 204)
        self.assertEqual(self.request('GET', f'/api/v1/orders?orderId={order_id}')[1], [])

    def test_task_generation_and_filtering_keep_order_relationship(self):
        # 生成済みタスクと工程順序を取得し、改称後も同じ親を参照することを確認する。
        _, orders = self.request('GET', '/api/v1/orders')
        order_id = orders[0]['orderId']
        status, tasks = self.request('GET', f'/api/v1/orders/{order_id}/tasks')
        self.assertEqual(status, 200)
        self.assertEqual([task['taskName'] for task in tasks], ['配合', '充填', '包装'])
        self.assertTrue(all(task['orderId'] == order_id and 'jobId' not in task for task in tasks))
        self.assertEqual(len(self.request('GET', f'/api/v1/orders/{order_id}/dependencies')[1]), 2)
        self.assertEqual(len(self.request('GET', f'/api/v1/tasks?orderId={order_id}')[1]), 3)
        status, regenerated = self.request('POST', f'/api/v1/orders/{order_id}/generate-tasks?replace=true')
        self.assertEqual(status, 200, regenerated)
        self.assertEqual(len(regenerated), 3)

    def test_order_attribute_uses_same_value_in_api_and_db(self):
        # ORDER区分が変換されずに保存・検索されることを確認する。
        attribute = AttributeDefinition(
            OrganizationID=self.seeded['organizationId'], EntityType='ORDER',
            AttributeKey='order_attribute', Label='オーダー属性',
        )
        self.db.add(attribute)
        self.db.commit()
        self.assertEqual(self.db.execute(text('SELECT EntityType FROM M_AttributeDefinitions WHERE AttributeKey = :key'), {'key': 'order_attribute'}).scalar_one(), 'ORDER')
        self.db.expire_all()
        self.assertEqual(self.db.get(AttributeDefinition, attribute.AttributeDefID).EntityType, 'ORDER')

        # APIでORDERを指定した絞り込みで、保存済みの属性を取得する。
        status, attributes = self.request('GET', '/api/v1/attribute-definitions?entityType=ORDER')
        self.assertEqual(status, 200, attributes)
        self.assertEqual([row['attributeKey'] for row in attributes], ['order_attribute'])
        self.assertEqual(attributes[0]['entityType'], 'ORDER')

    def test_existing_plan_data_board_approval_compare_and_dispatch(self):
        # 計算エンジンの入出力を使い、計算後の各画面と承認の関連処理を確認する。
        status, plan = self.request('POST', '/api/v1/plans', {
            'siteId': self.seeded['siteId'], 'horizonStart': '2026-10-26T21:00:00Z',
            'horizonEnd': '2026-10-29T21:00:00Z',
        })
        self.assertEqual(status, 201, plan)
        plan_id = plan['planId']
        stored_plan = self.db.get(Plan, plan_id)
        problem = build_problem(self.db, stored_plan)
        task = next(iter(problem.tasks.values()))
        option = task.options[0]
        # 最適化ライブラリを使わず、1件の割付を計算結果と同じ経路で保存する。
        write_results(self.db, stored_plan, problem, [SAssignment(task.id, option.resource_id, 0, option.duration)], 'test')
        self.db.add(PlanViolation(PlanID=plan_id, Severity='SOFT', ViolationCode='LATE_ORDER', Message='保存名確認'))
        self.db.commit()
        self.assertEqual(self.db.execute(text('SELECT COUNT(*) FROM T_PlanKpis WHERE KpiKey = :key'), {'key': 'late_orders'}).scalar_one(), 1)
        self.assertEqual(self.db.execute(text('SELECT COUNT(*) FROM T_PlanViolations WHERE ViolationCode = :code'), {'code': 'LATE_ORDER'}).scalar_one(), 1)
        self.db.expire_all()

        # DBと各APIで同じ名称を使用することを確認する。
        _, kpis = self.request('GET', f'/api/v1/plans/{plan_id}/kpis')
        self.assertIn('late_orders', kpis)
        self.assertNotIn('late_jobs', kpis)
        _, board = self.request('GET', f'/api/v1/plans/{plan_id}/board')
        self.assertIn('orderNo', board['events'][0])
        self.assertIn('orderId', board['unscheduled'][0])
        self.assertIn('type', board['resources'][0])
        self.assertNotIn('kind', board['resources'][0])
        self.assertTrue(any(issue['code'] == 'LATE_ORDER' for issue in board['issues']))
        _, assignments = self.request('GET', f'/api/v1/plans/{plan_id}/assignments')
        self.assertEqual(assignments[0]['orderId'], task.order_id)
        _, violations = self.request('GET', f'/api/v1/plans/{plan_id}/violations')
        self.assertTrue(any(issue['violationCode'] == 'LATE_ORDER' for issue in violations))

        # コピー・比較でも集計名を維持し、承認時は所属オーダーだけを計画済みにする。
        status, copied = self.request('POST', f'/api/v1/plans/{plan_id}/copy')
        self.assertEqual(status, 201, copied)
        status, comparison = self.request('GET', f"/api/v1/plans/compare?a={plan_id}&b={copied['planId']}")
        self.assertEqual(status, 200, comparison)
        self.assertIn('late_orders', {item['key'] for item in comparison['kpis']})
        status, approved = self.request('POST', f'/api/v1/plans/{plan_id}/approve')
        self.assertEqual(status, 200, approved)
        self.assertEqual(self.db.get(Order, task.order_id).Status, 'PLANNED')
        status, dispatch = self.request('GET', f"/api/v1/dispatch?siteId={self.seeded['siteId']}&date=2026-10-27")
        self.assertEqual(status, 200, dispatch)
        items = [item for resource in dispatch['resources'] for item in resource['items']]
        self.assertEqual(len(items), 1)
        self.assertIn('orderNo', items[0])

    def test_api_schema_and_other_masters_keep_their_fields(self):
        # 自動生成された型と、影響を受けないリソースAPIの項目を確認する。
        schemas = app.openapi()['components']['schemas']
        self.assertIn('orderId', schemas['OrderRead']['properties'])
        self.assertIn('parentOrderId', schemas['OrderRead']['properties'])
        self.assertIn('orderId', schemas['TaskRead']['properties'])
        self.assertEqual(schemas['OrderCreate']['properties']['orderName']['type'], 'string')
        status, resources = self.request('GET', '/api/v1/resources')
        self.assertEqual(status, 200)
        self.assertEqual(len(resources), 6)
        self.assertIn('resourceId', resources[0])
        self.assertEqual(resources[0]['resourceType'], 'MACHINE')
        self.assertNotIn('resourceKind', resources[0])
        # 共通の型生成変更が、従来のリソース登録・更新・削除にも影響しないことを確認する。
        status, resource = self.request('POST', '/api/v1/resources', {
            'siteId': self.seeded['siteId'], 'resourceCode': 'ORDER-TEST', 'resourceName': '関連機能確認',
        })
        self.assertEqual(status, 201, resource)
        self.assertEqual(resource['resourceType'], 'MACHINE')
        status, updated = self.request('PATCH', f"/api/v1/resources/{resource['resourceId']}", {'resourceName': '更新後', 'resourceType': 'PERSON'})
        self.assertEqual(status, 200, updated)
        self.assertEqual(updated['resourceName'], '更新後')
        self.assertEqual(updated['resourceType'], 'PERSON')
        self.assertEqual([row['resourceId'] for row in self.request('GET', '/api/v1/resources?resourceType=PERSON')[1]], [resource['resourceId']])
        self.assertEqual(self.request('DELETE', f"/api/v1/resources/{resource['resourceId']}")[0], 204)
        # タスクがOrderID列を通じて親オーダーへ関連付けられることを確認する。
        task = self.db.scalar(select(Task))
        self.assertEqual(task.order.OrderID, task.OrderID)
        self.assertEqual(Order.__tablename__, 'T_Orders')
        self.assertNotIn('T_Jobs', Base.metadata.tables)
        self.assertIn('OrderID', Task.__table__.columns)
        self.assertNotIn('JobID', Task.__table__.columns)

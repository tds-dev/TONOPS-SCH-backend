"""実設定・実DB・外部通信を使わず、工程の曜日制限・移行判断と既存機能を確認する。"""
import asyncio
import json
import re
import sys
import types
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI, HTTPException
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from asgi_helpers import request

# 設定ファイルを読まず、テスト対象外の接続設定だけをメモリDB用に置き換える。
config = types.ModuleType("app.core.config")
config.get_settings = lambda: SimpleNamespace(database_url="sqlite:///:memory:", app_timezone="Asia/Tokyo",
                                             default_user="weekday-test", worker_poll_seconds=2)
# 接続設定だけを差し替え、読み込んだモデルやAPIのモジュールは削除しない。
previous_config = sys.modules.get("app.core.config")
sys.modules["app.core.config"] = config
try:
    from app import models
    from app.core.db import Base, get_db, make_engine
    from app.engine.problem import PTask, Problem
    from app.engine.result import SAssignment
    from app.engine.snapshot import build_problem
    from app.engine.weekdays import blocked_ranges, check_weekday_restrictions
    from app.models.masters import Location, Product, ProductProcess
    from app.models.transactions import Plan, PlanAssignment, PlanViolation, Task
    from app.routers.masters import routers as master_routers
    from app.routers.plans import router as plan_router
    from app.schemas.base import schemas_for
    from app.services.board_service import build_board
    from app.services.demo_seed import seed_demo
    from app.services.plan_lifecycle import blocks_plan_approval, copy_plan
    from app.services.product_process_service import save_product_process
    from app.services.product_validation import validate_weekday_settings
    from app.services.task_conditions import TaskWeekdayRestriction
finally:
    # ほかのテストが使う設定モジュールだけを元に戻す。
    if previous_config is None:
        sys.modules.pop("app.core.config", None)
    else:
        sys.modules["app.core.config"] = previous_config

from DataBase.migrate_process_weekdays import inspect_migration, plan_restrictions


# 毎回独立したメモリDBを使い、製品工程・割付・違反の保持を確認する。
class ProcessWeekdaysTest(unittest.TestCase):
    # 構造の変更を実際に適用した空のDBと、最低限の製品を用意する。
    def setUp(self):
        self.engine = make_engine("sqlite:///:memory:", poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine, expire_on_commit=False)
        self.db.add(Location(LocationID=1, LocationName="テスト拠点"))
        self.db.flush()
        self.db.add(Product(ProductID=1, LocationID=1, ProductName="製品A"))
        self.db.commit()
        # 画面と同じAPIを通し、同期処理のスレッド間でも同じメモリDBを使う。
        self.app = FastAPI()
        for router in master_routers:
            self.app.include_router(router, prefix="/api/v1")
        self.app.dependency_overrides[get_db] = lambda: self.db

    # テストのデータを破棄し、実DBには接続しない。
    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    # 外部通信を行わず、実際のJSON解析・入力検証・保存・応答を通して確認する。
    def call(self, method: str, path: str, body=None):
        return asyncio.run(request(self.app, method, "/api/v1" + path, body))

    # 画面の4項目を登録し、一覧・単件取得・部分更新・解除・再有効化まで確認する。
    def test_api_create_get_update_and_clear_weekday_settings(self):
        status, created = self.call("POST", "/product-processes", {
            "productId": 1, "sequenceNumber": 1, "processName": "混合", "allowedWeekdaysJSON": [5, 1, 3],
            "weekdayRestrictionEnabled": True, "weekdayRestrictionStartAt": "2026-11-13T00:00:00.123456Z",
            "weekdayRestrictionEndAt": "2026-11-20T18:00:00+09:00",
        })
        self.assertEqual(status, 201, created)
        self.assertEqual(created["allowedWeekdaysJSON"], [1, 3, 5])
        self.assertEqual(created["weekdayRestrictionStartAt"], "2026-11-13T09:00:00.123456+09:00")
        path = f"/product-processes/{created['productProcessId']}"
        self.assertEqual(self.call("GET", path), (200, created))
        self.assertEqual(self.call("GET", "/product-processes?productId=1")[1], [created])
        status, disabled = self.call("PATCH", path, {"weekdayRestrictionEnabled": False})
        self.assertEqual(status, 200, disabled)
        self.assertEqual(disabled["allowedWeekdaysJSON"], [1, 3, 5])
        self.assertEqual(disabled["weekdayRestrictionStartAt"], created["weekdayRestrictionStartAt"])
        status, enabled = self.call("PATCH", path, {"weekdayRestrictionEnabled": True,
                                                     "weekdayRestrictionStartAt": None, "weekdayRestrictionEndAt": None})
        self.assertEqual(status, 200, enabled)
        self.assertTrue(enabled["weekdayRestrictionEnabled"])
        self.assertIsNone(enabled["weekdayRestrictionStartAt"])
        self.assertIsNone(enabled["weekdayRestrictionEndAt"])
        self.assertEqual(enabled["allowedWeekdaysJSON"], [1, 3, 5])

    # 空曜日・不正値・部分更新による期間逆転を422で拒否し、他の更新も取り消す。
    def test_api_rejects_invalid_weekdays_and_keeps_saved_values(self):
        status, created = self.call("POST", "/product-processes", {
            "productId": 1, "sequenceNumber": 1, "processName": "混合", "allowedWeekdaysJSON": [1, 2, 3, 4, 5],
            "weekdayRestrictionStartAt": "2026-11-13T09:00:00+09:00", "weekdayRestrictionEndAt": "2026-11-20T18:00:00+09:00",
        })
        self.assertEqual(status, 201, created)
        path = f"/product-processes/{created['productProcessId']}"
        for values in ([{"allowedWeekdaysJSON": days} for days in [None, [], [7], [-1], [1, 1], ["1"], [True], [1.5]]]
                       + [{"weekdayRestrictionEnabled": None}, {"weekdayRestrictionEndAt": "2026-11-13T08:59:59+09:00"},
                          {"weekdayRestrictionStartAt": "2026-11-21T09:00:00+09:00"}, {"weekdayRestrictionStartAt": "invalid"}]):
            with self.subTest(values=values):
                status, result = self.call("PATCH", path, {"processName": "変更されない名前", **values})
                self.assertEqual(status, 422, result)
                self.assertEqual(self.call("GET", path)[1], created)

    # 従来の項目だけの新規登録と、工程番号交換でも工程ごとの曜日を保持する。
    def test_api_defaults_and_reordering_preserve_each_process_setting(self):
        status, first = self.call("POST", "/product-processes", {"productId": 1, "sequenceNumber": 1, "processName": "混合"})
        self.assertEqual(status, 201, first)
        self.assertEqual(first["allowedWeekdaysJSON"], list(range(7)))
        self.assertTrue(first["weekdayRestrictionEnabled"])
        status, second = self.call("POST", "/product-processes", {
            "productId": 1, "sequenceNumber": 2, "processName": "加熱", "minLagAfterMin": 30, "maxLagAfterMin": 60,
            "allowedWeekdaysJSON": [1, 3, 5], "weekdayRestrictionEnabled": False,
        })
        self.assertEqual(status, 201, second)
        path = f"/product-processes/{first['productProcessId']}"
        status, moved = self.call("PATCH", path, {"sequenceNumber": 2, "processName": "混合工程"})
        self.assertEqual(status, 200, moved)
        self.assertEqual(moved["allowedWeekdaysJSON"], list(range(7)))
        second_saved = self.call("GET", f"/product-processes/{second['productProcessId']}")[1]
        self.assertEqual(second_saved["sequenceNumber"], 1)
        self.assertEqual(second_saved["allowedWeekdaysJSON"], [1, 3, 5])
        self.assertFalse(second_saved["weekdayRestrictionEnabled"])
        self.assertEqual((second_saved["minLagAfterMin"], second_saved["maxLagAfterMin"]), (30, 60))

    # 新規工程は制限なしとし、既存画面から名称だけ更新しても曜日設定を保持する。
    def test_defaults_and_partial_update_preserve_weekdays(self):
        process = save_product_process(self.db, None, {"ProductID": 1, "SequenceNumber": 1, "ProcessName": "混合"}, "test")
        self.db.commit()
        self.assertEqual(process.AllowedWeekdaysJSON, list(range(7)))
        process.AllowedWeekdaysJSON = [1, 3, 5]
        self.db.commit()
        save_product_process(self.db, process, {"ProcessName": "混合工程"}, "test")
        self.db.commit()
        self.assertEqual(process.AllowedWeekdaysJSON, [1, 3, 5])
        self.assertEqual(process.ProcessName, "混合工程")

    # APIと計算時の共通チェックが、不正な曜日・期間を拒否する。
    def test_invalid_settings_are_rejected(self):
        for weekdays in [None, [], [True], [-1], [7], [1, 1], ["1"], {}]:
            with self.subTest(weekdays=weekdays), self.assertRaises(HTTPException):
                validate_weekday_settings(None, {"AllowedWeekdaysJSON": weekdays})
        for values in [{"WeekdayRestrictionEnabled": None},
                       {"WeekdayRestrictionStartAt": datetime(2026, 11, 14), "WeekdayRestrictionEndAt": datetime(2026, 11, 13)}]:
            with self.subTest(values=values), self.assertRaises(HTTPException):
                validate_weekday_settings(None, values)

    # 追加した日時項目も、既存APIと同じ日本時間へ正規化される。
    def test_api_datetime_schema_normalizes_japan_time(self):
        _, _, update = schemas_for(ProductProcess)
        values = update.model_validate({"allowedWeekdaysJSON": [1, 2],
                                        "weekdayRestrictionStartAt": "2026-11-13T00:00:00Z"}).model_dump(exclude_unset=True)
        self.assertEqual(values["WeekdayRestrictionStartAt"], datetime(2026, 11, 13, 9))
        validate_weekday_settings(None, values)

    # 有効期間の境界を含め、制限無効時だけ曜日チェックを外す。
    def test_period_boundaries_and_disabled_setting(self):
        start, end = datetime(2026, 11, 13, 9), datetime(2026, 11, 20, 18)
        setting = TaskWeekdayRestriction([1, 2, 3, 4, 5], True, start, end)
        self.assertEqual(setting.allowed_at(start), [1, 2, 3, 4, 5])
        self.assertEqual(setting.allowed_at(end), [1, 2, 3, 4, 5])
        self.assertIsNone(setting.allowed_at(start - timedelta(seconds=1)))
        self.assertIsNone(setting.allowed_at(end + timedelta(seconds=1)))
        setting.enabled = False
        self.assertIsNone(setting.allowed_at(start))

    # 禁止日の開始直前までを許可し、日付をまたいだ作業は検出する。
    def test_whole_assignment_and_locked_behavior(self):
        problem = Problem(datetime(2026, 11, 13), 3 * 1440, "Asia/Tokyo", {},
                          {1: PTask(1, 1, "混合", {}, [], allowed_weekdays=[1, 2, 3, 4, 5])}, {})
        self.assertEqual(blocked_ranges(problem, [1, 2, 3, 4, 5]), [(1440, 2880), (2880, 4320)])
        self.assertEqual(check_weekday_restrictions(problem, [SAssignment(1, 1, 1380, 1440)]), [])
        violations = check_weekday_restrictions(problem, [SAssignment(1, 1, 1380, 1441)])
        self.assertEqual([(v.severity, v.code, v.task_id) for v in violations], [("HARD", "WEEKDAY", 1)])
        self.assertEqual(check_weekday_restrictions(problem, [SAssignment(1, 1, 1380, 1441, locked=True)]), [])

    # 旧テーブルと旧APIがなくても、段取り替えAPIを残す。
    def test_removed_tables_and_routes(self):
        self.assertNotIn("M_AttributeDefinitions", Base.metadata.tables)
        self.assertNotIn("M_Rules", Base.metadata.tables)
        self.assertNotIn("RuleID", PlanViolation.__table__.columns)
        paths = {route.path for router in [*master_routers, plan_router] for route in router.routes}
        self.assertFalse(any(path.startswith(("/rules", "/rule-types", "/attribute-definitions")) for path in paths))
        self.assertIn("/product-switch-times", paths)

    # SQLとPythonの初期データを実際に投入し、工程順・段取り替え・作業属性を維持する。
    def test_python_and_sql_seed_use_process_weekdays(self):
        for mode in ["python", "sql"]:
            with self.subTest(mode=mode):
                engine = make_engine("sqlite:///:memory:")
                Base.metadata.create_all(engine)
                try:
                    with Session(engine) as db:
                        if mode == "python":
                            seed_demo(db, now=datetime(2026, 11, 8, 12))
                        else:
                            sql = (Path(__file__).parents[1] / "DataBase/query/seed_demo_sqlserver.sql").read_text(encoding="utf-8")
                            for line in sql.splitlines():
                                if line.startswith(("INSERT INTO ", "UPDATE [M_Locations]")):
                                    db.execute(text(re.sub(r"\bN'", "'", line)))
                            db.commit()
                        plan = db.scalar(select(Plan).order_by(Plan.PlanID))
                        problem = build_problem(db, plan)
                        self.assertEqual((len(problem.tasks), len(problem.dependencies)), (21, 14))
                        self.assertTrue(problem.changeovers)
                        self.assertTrue(all(task.attrs.get("family") for task in problem.tasks.values()))
                        self.assertTrue(all(task.allowed_weekdays == [1, 2, 3, 4, 5]
                                            for task in problem.tasks.values() if task.attrs["family"] == "ナッツ入り"))
                        task_id = next(iter(problem.tasks))
                        process = db.get(ProductProcess, db.get(Task, task_id).ProductProcessID)
                        process.AllowedWeekdaysJSON = [0]
                        db.commit()
                        self.assertEqual(build_problem(db, plan).tasks[task_id].allowed_weekdays, [0])
                finally:
                    engine.dispose()

    # ルールIDを除いても、違反メッセージ・コピー・承認判定と段取り替え色分けを保持する。
    def test_violation_copy_board_and_approval(self):
        seed_demo(self.db, now=datetime(2026, 11, 8, 12))
        plan = self.db.scalar(select(Plan).order_by(Plan.PlanID))
        problem = build_problem(self.db, plan)
        task = next(iter(problem.tasks.values()))
        resource = task.options[0].resource_id
        self.db.add(PlanAssignment(PlanID=plan.PlanID, TaskID=task.id, ResourceID=resource,
                                   StartAt=plan.StartAt, EndAt=plan.StartAt + timedelta(minutes=30)))
        violation = PlanViolation(PlanID=plan.PlanID, TaskID=task.id, Severity="HARD", Message="曜日制限")
        self.db.add(violation)
        self.db.commit()
        self.assertTrue(blocks_plan_approval(violation, {task.id}))
        copied = copy_plan(self.db, plan, "test", name="曜日確認コピー")
        copied_violation = self.db.scalar(select(PlanViolation).where(PlanViolation.PlanID == copied.PlanID))
        self.assertEqual(copied_violation.Message, "曜日制限")
        board = build_board(self.db, copied)
        self.assertEqual(len(board["events"]), 1)
        self.assertEqual(board["events"][0]["colorValue"], str(problem.orders[task.order_id].product_id))

    # 同じ工程の作業が同じ対象条件なら、旧曜日ルールを工程設定へ変換する。
    def test_migration_preserves_dates_and_rejects_ambiguous_tasks(self):
        rule = {"RuleID": 1, "LocationID": 1, "RuleTypeKey": "allowed_weekdays", "SelectorJSON": {"family": "A"},
                "ParamsJSON": {"weekdays": [1, 2, 3, 4, 5]}, "IsActive": True,
                "ValidFrom": "2026-11-13", "ValidTo": "2026-11-20"}
        processes = [{"ProductProcessID": 1, "LocationID": 1}]
        tasks = [{"ProductProcessID": 1, "AttributesJSON": {"family": "A"}}]
        settings = plan_restrictions([rule], processes, tasks)[1]
        self.assertEqual(settings["WeekdayRestrictionEndAt"], datetime(2026, 11, 20, 23, 59, 59, 999999))
        with self.assertRaises(ValueError):
            plan_restrictions([rule], processes, tasks + [{"ProductProcessID": 1, "AttributesJSON": {"family": "B"}}])
        with self.assertRaises(ValueError):
            plan_restrictions([rule, {**rule, "ValidFrom": "2026-11-14"}], processes, tasks)

    # 旧ルールの実テーブルを読み取り、削除前にデモ3工程へ移せることを確認する。
    def test_migration_inspection_reads_legacy_tables_without_writes(self):
        seeded = seed_demo(self.db, now=datetime(2026, 11, 8, 12))
        self.db.execute(text("CREATE TABLE M_Rules (RuleID INTEGER PRIMARY KEY, LocationID INTEGER, "
                             "RuleTypeKey TEXT, SelectorJSON TEXT, ParamsJSON TEXT, IsActive BOOLEAN, "
                             "IsHard BOOLEAN, ValidFrom DATE, ValidTo DATE)"))
        self.db.execute(text("INSERT INTO M_Rules VALUES (1,:location,'allowed_weekdays',:selector,:params,1,1,NULL,NULL)"),
                        {"location": seeded["locationId"], "selector": json.dumps({"family": "ナッツ入り"}),
                         "params": json.dumps({"weekdays": [1, 2, 3, 4, 5]})})
        self.db.commit()
        settings = inspect_migration(self.db.connection())
        self.assertEqual(len(settings), 3)
        self.assertTrue(all(setting["AllowedWeekdaysJSON"] == [1, 2, 3, 4, 5] for setting in settings.values()))
        self.assertEqual(self.db.scalar(text("SELECT COUNT(*) FROM M_Rules")), 1)


if __name__ == "__main__":
    unittest.main()

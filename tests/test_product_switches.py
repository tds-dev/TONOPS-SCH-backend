"""製品工程IDによる段取り替えのAPI・任意指定・計算・削除保護・色分けを確認する。"""
import importlib.util
import unittest
from datetime import datetime

from sqlalchemy import event, select, update
from sqlalchemy.dialects import mssql
from sqlalchemy.exc import IntegrityError

import test_process_weekdays as weekday_tests

from app.engine.edit import recompute_setups
from app.engine.evaluate import check_schedule
from app.engine.problem import PChangeover, POption, POrder, PResource, PTask, Problem
from app.engine.result import SAssignment
from app.engine.snapshot import build_problem
from app.models.masters import Product, ProductProcess, ProductSwitchRule, Resource, ResourceGroup
from app.models.transactions import Plan, Task
from app.services.board_service import build_board
from app.services.demo_seed import seed_demo


# 実設定を読まない共通のDB・API準備を再利用し、段取り替えの変更点だけを確認する。
class ProductSwitchTest(unittest.TestCase):
    # 同名工程でも製品が異なる場合と、別拠点の誤指定を判定するデータを用意する。
    def setUp(self):
        weekday_tests.ProcessWeekdaysTest.setUp(self)
        self.db.add(weekday_tests.Location(LocationID=2, LocationName="別拠点"))
        self.db.add_all([Product(ProductID=2, LocationID=1, ProductName="製品B"),
                         Product(ProductID=3, LocationID=2, ProductName="別拠点製品")])
        self.db.flush()
        self.db.add_all([ProductProcess(ProductProcessID=1, ProductID=1, SequenceNumber=1, ProcessName="混合"),
                         ProductProcess(ProductProcessID=2, ProductID=1, SequenceNumber=2, ProcessName="加熱"),
                         ProductProcess(ProductProcessID=3, ProductID=2, SequenceNumber=1, ProcessName="混合"),
                         ProductProcess(ProductProcessID=4, ProductID=3, SequenceNumber=1, ProcessName="混合"),
                         ResourceGroup(ResourceGroupID=1, LocationID=1, GroupName="混合設備"),
                         ResourceGroup(ResourceGroupID=2, LocationID=2, GroupName="別拠点設備")])
        self.db.flush()
        self.db.add(Resource(ResourceID=1, LocationID=1, ResourceGroupID=1, ResourceName="設備A"))
        self.db.commit()

    # 共通の後処理を使い、テスト間でデータを共有しない。
    def tearDown(self):
        weekday_tests.ProcessWeekdaysTest.tearDown(self)

    # 実際のHTTP接続を開かず、画面と同じAPIを呼び出す。
    def call(self, method, path, body=None):
        return weekday_tests.ProcessWeekdaysTest.call(self, method, path, body)

    # テスト用の段取り替え設定を、登録API経由で作成する。
    def create_setting(self, **values):
        status, setting = self.call("POST", "/product-switch-times", {
            "locationId": 1, "productSwitchTimeName": "工程切替", "resourceGroupId": 1, **values,
        })
        self.assertEqual(status, 201, setting)
        self.assertNotIn("attributeKey", setting)
        return setting["productSwitchTimeId"]

    # 工程選択・任意指定・取得・部分更新が、廃止した属性列なしで成立する。
    def test_api_create_update_and_wildcards(self):
        setting_id = self.create_setting()
        status, rule = self.call("POST", "/product-switch-rules", {
            "productSwitchTimeId": setting_id, "fromProductProcessId": 1, "toProductProcessId": 3,
            "setupMinutes": 30, "isForbidden": False,
        })
        self.assertEqual(status, 201, rule)
        self.assertNotIn("fromValue", rule)
        self.assertNotIn("toValue", rule)
        path = f"/product-switch-rules/{rule['productSwitchRuleId']}"
        self.assertEqual(self.call("GET", path)[1]["fromProductProcessId"], 1)
        status, updated = self.call("PATCH", path, {"toProductProcessId": None, "isForbidden": True})
        self.assertEqual(status, 200, updated)
        self.assertEqual(updated["fromProductProcessId"], 1)
        self.assertIsNone(updated["toProductProcessId"])
        self.assertEqual(updated["setupMinutes"], 30)
        self.assertTrue(updated["isForbidden"])
        status, duplicate = self.call("POST", "/product-switch-rules", {
            "productSwitchTimeId": setting_id, "fromProductProcessId": 1,
        })
        self.assertEqual(status, 409, duplicate)
        status, any_rule = self.call("POST", "/product-switch-rules", {"productSwitchTimeId": setting_id})
        self.assertEqual(status, 201, any_rule)
        self.assertIsNone(any_rule["fromProductProcessId"])
        self.assertIsNone(any_rule["toProductProcessId"])

    # 存在しない工程・別拠点・不正な時間や状態を保存せず、元の設定を保つ。
    def test_api_rejects_invalid_references_and_values(self):
        setting_id = self.create_setting()
        status, rule = self.call("POST", "/product-switch-rules", {
            "productSwitchTimeId": setting_id, "fromProductProcessId": 1, "toProductProcessId": 3,
        })
        self.assertEqual(status, 201, rule)
        path = f"/product-switch-rules/{rule['productSwitchRuleId']}"
        for values in [{"fromProductProcessId": 999}, {"toProductProcessId": 4}, {"setupMinutes": -1},
                       {"isForbidden": None}, {"productSwitchTimeId": 999}]:
            with self.subTest(values=values):
                status, result = self.call("PATCH", path, values)
                self.assertEqual(status, 422, result)
                self.assertEqual(self.call("GET", path)[1], rule)
        for values in [{"resourceGroupId": 2}, {"resourceGroupId": 999}, {"defaultMinutes": -1}, {"isActive": None}]:
            with self.subTest(values=values):
                self.assertEqual(self.call("POST", "/product-switch-times", {
                    "locationId": 1, "productSwitchTimeName": "不正設定", **values,
                })[0], 422)

    # 具体的な条件と任意指定を、更新によって重複させることも禁止する。
    def test_duplicate_update_and_foreign_keys(self):
        setting_id = self.create_setting()
        for before, after in [(1, 3), (None, None)]:
            status, rule = self.call("POST", "/product-switch-rules", {
                "productSwitchTimeId": setting_id, "fromProductProcessId": before, "toProductProcessId": after,
            })
            self.assertEqual(status, 201, rule)
        path = f"/product-switch-rules/{rule['productSwitchRuleId']}"
        self.assertEqual(self.call("PATCH", path, {"fromProductProcessId": 1, "toProductProcessId": 3})[0], 409)
        # APIを経由しない保存でも、存在しない工程IDはDBの外部キーで拒否する。
        with self.assertRaises(IntegrityError):
            self.db.add(ProductSwitchRule(ProductSwitchTimeID=setting_id, FromProductProcessID=999, ToProductProcessID=1))
            self.db.commit()
        self.db.rollback()

    # 参照中の工程を保護し、親設定の削除ではその設定の明細だけを連動削除する。
    def test_process_delete_protection_and_parent_cascade(self):
        setting_id = self.create_setting()
        status, rule = self.call("POST", "/product-switch-rules", {
            "productSwitchTimeId": setting_id, "fromProductProcessId": 1, "toProductProcessId": 3,
        })
        self.assertEqual(status, 201, rule)
        self.assertEqual(self.call("DELETE", "/product-processes/1")[0], 409)
        self.assertEqual(self.call("DELETE", "/product-processes/3")[0], 409)
        self.assertEqual(self.call("DELETE", f"/product-switch-times/{setting_id}")[0], 204)
        self.assertEqual(self.call("GET", f"/product-switch-rules/{rule['productSwitchRuleId']}")[0], 404)
        self.assertEqual(self.call("DELETE", "/product-processes/3")[0], 204)

    # 工程候補は製品の所属拠点で絞り、削除済み製品の工程は選択対象にしない。
    def test_process_options_filter_by_location(self):
        status, rows = self.call("GET", "/product-processes?locationId=1")
        self.assertEqual(status, 200, rows)
        self.assertEqual({row["productProcessId"] for row in rows}, {1, 2, 3})
        self.assertEqual([row["productProcessId"] for row in self.call("GET", "/product-processes?locationId=2")[1]], [4])
        self.assertEqual(self.call("GET", "/product-processes?locationId=invalid")[0], 422)
        self.db.get(Product, 2).DeleteFlag = True
        self.db.commit()
        self.assertEqual({row["productProcessId"] for row in self.call("GET", "/product-processes?locationId=1")[1]}, {1, 2})

    # 同じ設備に複数の有効設定を重ねず、無効な設定は切替候補として保持できる。
    def test_overlapping_active_settings_are_rejected(self):
        setting_id = self.create_setting()
        for group in [1, None]:
            status, result = self.call("POST", "/product-switch-times", {
                "locationId": 1, "productSwitchTimeName": "重複設定", "resourceGroupId": group,
            })
            self.assertEqual(status, 409, result)
        inactive_id = self.create_setting(isActive=False)
        path = f"/product-switch-times/{inactive_id}"
        self.assertEqual(self.call("PATCH", path, {"isActive": True})[0], 409)
        self.assertEqual(self.call("PATCH", f"/product-switch-times/{setting_id}", {"isActive": False})[0], 200)
        self.assertEqual(self.call("PATCH", path, {"isActive": True})[0], 200)

    # SQL ServerのBIT列はIS 1ではなく= 1で比較し、SQLiteとの差を検出する。
    def test_sqlserver_boolean_filter_syntax(self):
        statements = []

        # APIが実際に使った条件式を、DB接続なしでSQL Server向けにも変換する。
        def record_statement(context):
            statements.append(context.statement)

        event.listen(self.db, "do_orm_execute", record_statement)
        try:
            self.assertEqual(self.call("GET", "/product-processes?locationId=1")[0], 200)
            self.create_setting()
        finally:
            event.remove(self.db, "do_orm_execute", record_statement)
        # NULLの任意指定はIS NULLを維持し、BITの比較だけを等価条件にする。
        compiled = "\n".join(str(statement.compile(dialect=mssql.dialect(), compile_kwargs={"literal_binds": True}))
                             for statement in statements)
        self.assertNotRegex(compiled, r"\bIS\s+[01]\b")
        self.assertIn("[DeleteFlag] = 0", compiled)
        self.assertIn("[IsActive] = 1", compiled)

    # 個別・片側任意・両側任意・既定時間の優先順位と、同一工程の従来動作を確認する。
    def test_lookup_priority_and_same_process(self):
        changeover = PChangeover(1, {1}, 90, {
            (1, 3): (30, False), (1, None): (20, False), (None, 3): (10, True), (None, None): (5, False),
        })
        self.assertEqual(changeover.lookup(1, 3), (30, False))
        self.assertEqual(changeover.lookup(1, 2), (20, False))
        self.assertEqual(changeover.lookup(2, 3), (10, True))
        self.assertEqual(changeover.lookup(2, 4), (5, False))
        self.assertEqual(changeover.lookup(1, 1), (0, False))
        self.assertEqual(changeover.lookup(None, 1), (0, False))
        changeover.entries.clear()
        self.assertEqual(changeover.lookup(1, 3), (90, False))
        changeover.entries[(1, 1)] = (4, True)
        self.assertEqual(changeover.lookup(1, 1), (4, True))

    # 作業属性を持たない2作業でも、工程IDから切替時間と禁止順序を判定する。
    def problem(self):
        return Problem(datetime(2026, 11, 9, 6), 240, "Asia/Tokyo", {1: PResource(1, "設備", 1, [(0, 240)])},
                       {1: PTask(1, 1, "製品Aの混合", {}, [POption(1, 10)], product_process_id=1),
                        2: PTask(2, 2, "製品Bの混合", {}, [POption(1, 10)], product_process_id=3)},
                       {1: POrder(1, "A", None), 2: POrder(2, "B", None)},
                       changeovers=[PChangeover(1, {1}, 0, {(1, 3): (30, False)})])

    # 手動配置の再計算と違反検証でも、同じ工程ペアの設定を使用する。
    def test_manual_setup_and_forbidden_sequence(self):
        problem = self.problem()
        assignments = [SAssignment(1, 1, 0, 10), SAssignment(2, 1, 20, 30)]
        self.assertIn("SETUP_TOO_SHORT", {issue.code for issue in check_schedule(problem, assignments)})
        assignments[1].start, assignments[1].end = 40, 50
        recompute_setups(problem, assignments, {1})
        self.assertEqual(assignments[1].setup, 30)
        self.assertEqual(check_schedule(problem, assignments), [])
        problem.changeovers[0].entries[(1, 3)] = (30, True)
        self.assertIn("FORBIDDEN_SEQUENCE", {issue.code for issue in check_schedule(problem, assignments)})

    # 仮データの分類を消しても、工程IDから22組の切替設定と製品色分けを取得する。
    def test_snapshot_and_color_work_without_task_attributes(self):
        seed_demo(self.db, now=datetime(2026, 11, 8, 12))
        self.db.execute(update(Task).values(AttributesJSON=None))
        self.db.commit()
        self.db.expire_all()
        plan = self.db.scalar(select(Plan).order_by(Plan.PlanID))
        problem = build_problem(self.db, plan)
        self.assertTrue(all(task.attrs == {} for task in problem.tasks.values()))
        self.assertEqual(len(problem.changeovers[0].entries), 22)
        pair, (minutes, _) = next(iter(problem.changeovers[0].entries.items()))
        self.assertEqual(problem.changeovers[0].lookup(*pair), (minutes, False))
        board = build_board(self.db, plan)
        self.assertEqual(board["colorBy"], "productId")
        self.assertTrue(all(task["colorValue"] for task in board["unscheduled"]))

    # OR-Toolsを導入済みの環境では、実際の自動計算でも方向・切替時間を守る。
    @unittest.skipUnless(importlib.util.find_spec("ortools"), "OR-Tools未導入")
    def test_solver_enforces_switch_time_and_forbidden_direction(self):
        from app.engine.model_builder import solve_problem
        problem = self.problem()
        problem.changeovers[0].entries[(3, 1)] = (0, True)
        result = solve_problem(problem, workers=1)
        self.assertIn(result.status, {"OPTIMAL", "FEASIBLE"})
        assignments = {assignment.task_id: assignment for assignment in result.assignments}
        self.assertEqual(set(assignments), {1, 2})
        self.assertGreaterEqual(assignments[2].start, assignments[1].end + 30)
        self.assertEqual(assignments[2].setup, 30)
        self.assertEqual(check_schedule(problem, list(assignments.values())), [])


if __name__ == "__main__":
    unittest.main()

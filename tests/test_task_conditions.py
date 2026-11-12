"""製品マスタ編集の即時反映と、タスク・計画・実績を維持した計算・手動編集を確認する。"""
import re
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from test_order_crud import InMemoryApiTestCase, Settings

# 設定ファイル・実DBを読まず、計算・編集・仮データ処理を読み込む。
with patch("app.core.config.get_settings", return_value=Settings(
    _env_file=None, database_url="sqlite:///:memory:", default_user="condition-test",
)):
    from app.core.db import Base, make_engine
    from app.engine.evaluate import check_schedule
    from app.engine.model_builder import solve_problem
    from app.engine.result import SAssignment
    from app.engine.snapshot import build_problem
    from app.models.masters import CalculationSetting, Product, ProductProcess, ProductProcessResource, Resource, ResourceGroup
    from app.models.transactions import Order, Plan, PlanAssignment, Task, WorkActual
    from app.routers.board import router as board_router
    from app.services.demo_seed import seed_demo
    from app.services.task_conditions import build_task_conditions


# マスタ変更が画面・自動計算・手動配置へ一貫して反映されることを確認する。
class TaskConditionsTest(InMemoryApiTestCase):
    # 同一製品の3工程と設備グループ、個別設備候補を用意する。
    def setUp(self):
        super().setUp()
        self.app.include_router(board_router, prefix="/api/v1")
        self.db.add(Product(ProductID=1, LocationID=1, ProductName="製品"))
        self.db.add(ResourceGroup(ResourceGroupID=1, LocationID=1, GroupName="設備群"))
        self.db.flush()
        self.db.add_all([
            Resource(ResourceID=1, LocationID=1, ResourceGroupID=1, ResourceName="設備A"),
            Resource(ResourceID=2, LocationID=1, ResourceGroupID=1, ResourceName="設備B"),
            ProductProcess(ProductProcessID=1, ProductID=1, SequenceNumber=1, ProcessName="前処理", MinLagAfterMin=3, MaxLagAfterMin=9),
            ProductProcess(ProductProcessID=2, ProductID=1, SequenceNumber=2, ProcessName="加工", MinLagAfterMin=4, MaxLagAfterMin=12),
            ProductProcess(ProductProcessID=3, ProductID=1, SequenceNumber=3, ProcessName="包装", MinLagAfterMin=5),
        ])
        self.db.flush()
        self.db.add_all([
            ProductProcessResource(ProductProcessResourceID=1, ProductProcessID=1, ResourceID=1, SetupMinutes=2, FixedMinutes=3, MinutesPerUnit=2),
            ProductProcessResource(ProductProcessResourceID=2, ProductProcessID=2, ResourceGroupID=1, FixedMinutes=7),
            ProductProcessResource(ProductProcessResourceID=3, ProductProcessID=3, ResourceID=2, FixedMinutes=5),
        ])
        self.db.commit()

    # オーダーごとに作業を作り、以後のマスタ変更では作業を再生成しない。
    def create_order(self, number="ORDER", quantity=3):
        status, order = self.call("POST", "/orders", {
            "locationId": 1, "wbsNumber": number, "orderName": number, "productId": 1, "quantity": quantity,
        })
        self.assertEqual(status, 201, order)
        status, tasks = self.call("POST", f'/orders/{order["orderId"]}/generate-tasks')
        self.assertEqual(status, 200, tasks)
        return order, tasks

    # 保存済みタスクを使う下書き計画を作り、設備稼働はカレンダー未指定の全時間とする。
    def create_plan(self):
        self.db.add(CalculationSetting(CalculationSettingID=1, LocationID=1, CalculationSettingName="検証用", ObjectiveWeightsJSON={"unscheduled": 1000}))
        self.db.flush()
        plan = Plan(LocationID=1, PlanName="計画", Status="DRAFT", CalculationSettingID=1,
                    StartAt=datetime(2026, 11, 12, 6), EndAt=datetime(2026, 11, 13, 6))
        self.db.add(plan)
        self.db.commit()
        return plan

    # 候補・数量・待ち時間の変更と削除を、タスク再生成なしでAPIへ反映する。
    def test_api_uses_current_master_without_regenerating_tasks(self):
        order, tasks = self.create_order()
        path = f'/orders/{order["orderId"]}'
        self.assertEqual(tasks[0]["options"][0]["durationMin"], 11)
        self.assertEqual(self.call("PATCH", "/product-process-resources/1", {"resourceId": 2, "fixedMinutes": 8})[0], 200)
        self.assertEqual(self.call("PATCH", "/product-processes/1", {"minLagAfterMin": 6, "maxLagAfterMin": 15})[0], 200)
        self.assertEqual(self.call("PATCH", path, {"quantity": 8})[0], 200)
        updated = self.call("GET", path + "/tasks")[1]
        self.assertEqual([task["taskId"] for task in updated], [task["taskId"] for task in tasks])
        self.assertEqual(updated[0]["createdAt"], tasks[0]["createdAt"])
        self.assertEqual((updated[0]["options"][0]["resourceId"], updated[0]["options"][0]["durationMin"]), (2, 26))
        links = self.call("GET", path + "/dependencies")[1]
        self.assertEqual((links[0]["lagMin"], links[0]["maxLagMin"]), (6, 15))
        self.assertEqual(self.call("DELETE", "/product-process-resources/1")[0], 204)
        self.assertEqual(self.call("GET", path + "/tasks")[1][0]["options"], [])

    # マスタの工程交換を反映し、別オーダーのタスクを結ばない。
    def test_master_order_changes_links_without_mixing_orders(self):
        first, first_tasks = self.create_order("FIRST")
        second, second_tasks = self.create_order("SECOND")
        self.assertEqual(self.call("PATCH", "/product-processes/1", {"sequenceNumber": 3})[0], 200)
        for order, tasks in ((first, first_tasks), (second, second_tasks)):
            links = self.call("GET", f'/orders/{order["orderId"]}/dependencies')[1]
            self.assertEqual([(link["predecessorTaskId"], link["successorTaskId"], link["lagMin"]) for link in links],
                             [(tasks[2]["taskId"], tasks[1]["taskId"], 5), (tasks[1]["taskId"], tasks[0]["taskId"], 4)])
        # 対象から外れた中間工程を飛び越える関係を追加しない。
        selected = [self.db.get(Task, first_tasks[index]["taskId"]) for index in (0, 2)]
        self.assertEqual(build_task_conditions(self.db, selected).dependencies, [])

    # 自動計算・手動配置・検証が同じ最新条件を使い、作業状態・割付・実績は失われない。
    def test_solver_and_manual_edits_share_master_conditions(self):
        _, tasks = self.create_order()
        plan = self.create_plan()
        problem = build_problem(self.db, plan)
        self.assertEqual({option.resource_id for option in problem.tasks[tasks[1]["taskId"]].options}, {1, 2})
        solved = solve_problem(problem, workers=2)
        self.assertIn(solved.status, ("OPTIMAL", "FEASIBLE"))
        self.assertEqual(len(solved.assignments), 3)
        self.assertEqual(check_schedule(problem, solved.assignments), [])
        # ボードからの配置も、マスタから求めた11分を利用する。
        path = f"/plans/{plan.PlanID}/assignments"
        body = {"changes": [{"taskId": tasks[0]["taskId"], "resourceId": 1, "startAt": "2026-11-12T06:00:00"}]}
        status, response = self.call("PATCH", path, body)
        self.assertEqual(status, 200, response)
        assignment = self.db.scalar(select(PlanAssignment).where(PlanAssignment.TaskID == tasks[0]["taskId"]))
        self.assertEqual(assignment.EndAt - assignment.StartAt, timedelta(minutes=11))
        # 実績・進捗を持つタスクでも候補だけが新しいマスタへ追従する。
        task = self.db.get(Task, tasks[0]["taskId"])
        task.Status = "IN_PROGRESS"
        self.db.add(WorkActual(TaskID=task.TaskID, ResourceID=1, Status="IN_PROGRESS"))
        self.db.commit()
        self.assertEqual(self.call("PATCH", "/product-process-resources/1", {"resourceId": 2, "fixedMinutes": 8})[0], 200)
        changed = build_problem(self.db, plan)
        self.assertEqual([(option.resource_id, option.duration) for option in changed.tasks[task.TaskID].options], [(2, 16)])
        # 古い設備への配置は検証で違反として検出される。
        violations = check_schedule(changed, [SAssignment(task.TaskID, 1, 0, 11)])
        self.assertIn("NOT_ELIGIBLE", [violation.code for violation in violations])
        self.assertEqual(self.db.get(Task, task.TaskID).Status, "IN_PROGRESS")
        self.assertIsNotNone(self.db.get(PlanAssignment, assignment.AssignmentID))
        self.assertIsNotNone(self.db.scalar(select(WorkActual.WorkActualID)))
        # 更新後に未割付タスクを配置すると、新しい所要時間を使う。
        self.assertEqual(self.call("PATCH", path, {"changes": [{"assignmentId": assignment.AssignmentID, "remove": True, "isLocked": False}]})[0], 200)
        body["changes"][0]["resourceId"] = 2
        self.assertEqual(self.call("PATCH", path, body)[0], 200)
        moved = self.db.scalar(select(PlanAssignment).where(PlanAssignment.TaskID == task.TaskID))
        self.assertEqual(moved.EndAt - moved.StartAt, timedelta(minutes=16))

    # 廃止したテーブルと書込APIを作らず、既存の参照APIは維持する。
    def test_removed_tables_and_write_routes_are_absent(self):
        for name in ("T_TaskResourceOptions", "T_TaskDependencies"):
            self.assertNotIn(name, Base.metadata.tables)
        for path in ("/task-resource-options", "/dependencies"):
            self.assertEqual(self.call("POST", path, {})[0], 404)

    # 工程追加後に作業が未生成なら計算を止め、完了済み工程を未生成と誤判定しない。
    def test_missing_new_process_is_reported_before_planning(self):
        order, tasks = self.create_order()
        plan = self.create_plan()
        self.db.get(Task, tasks[1]["taskId"]).Status = "DONE"
        self.db.commit()
        problem = build_problem(self.db, plan)
        self.assertNotIn(tasks[1]["taskId"], problem.tasks)
        self.assertEqual(problem.dependencies, [])
        # 新たな工程の作業本体を作るまでは、既存工程だけの計画を作らない。
        self.assertEqual(self.call("POST", "/product-processes", {
            "productId": 1, "sequenceNumber": 2, "processName": "追加工程",
        })[0], 201)
        status, response = self.call("GET", f"/plans/{plan.PlanID}/board")
        self.assertEqual(status, 422, response)
        self.assertIn("追加工程", response["detail"])
        # オーダー詳細は取得可能なままとし、既存タスク・実績の確認を妨げない。
        self.assertEqual(len(self.call("GET", f'/orders/{order["orderId"]}/tasks')[1]), 3)

    # Python仮データと手動SQLの両方が、廃止テーブルなしで登録できることを確認する。
    def test_python_and_sql_seed_work_with_new_schema(self):
        for mode in ("python", "sql"):
            with self.subTest(mode=mode):
                # 実DBとは無関係な、空のメモリDBを方式ごとに作る。
                engine = make_engine("sqlite:///:memory:")
                Base.metadata.create_all(engine)
                try:
                    with Session(engine) as db:
                        if mode == "python":
                            seeded = seed_demo(db, now=datetime(2026, 11, 12, 12))
                            self.assertEqual(seeded["orders"], 7)
                        else:
                            # T-SQLのINSERT文だけを取り出し、文字列のN接頭辞をSQLite向けに外す。
                            sql = (Path(__file__).parents[1] / "DataBase/query/seed_demo_sqlserver.sql").read_text(encoding="utf-8-sig")
                            for line in sql.splitlines():
                                if line.startswith("INSERT INTO "):
                                    db.execute(text(re.sub(r"\bN'", "'", line)))
                            db.commit()
                        tasks = list(db.scalars(select(Task)).all())
                        self.assertEqual(len(tasks), 21)
                        conditions = build_task_conditions(db, tasks)
                        self.assertEqual(len(conditions.dependencies), 14)
                        self.assertEqual(sum(len(options) for options in conditions.options.values()), 21)
                        plan = db.scalar(select(Plan).order_by(Plan.PlanID))
                        problem = build_problem(db, plan)
                        self.assertEqual(len(problem.tasks), 21)
                        self.assertTrue(all(task.options for task in problem.tasks.values()))
                finally:
                    engine.dispose()

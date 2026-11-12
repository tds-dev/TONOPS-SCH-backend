"""2026-11-12のDB変更後も、初期データ・計画操作・実績保護・中止監視が動くことを確認する。"""
import re
import unittest
from datetime import datetime
from pathlib import Path
from threading import Event, Thread
from unittest.mock import Mock, patch

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from test_order_crud import InMemoryApiTestCase, Settings

# 実際の設定ファイルとDBを使わず、メモリDB用の処理だけを読み込む。
with patch("app.core.config.get_settings", return_value=Settings(
    _env_file=None, database_url="sqlite:///:memory:", default_user="schema-test",
)):
    from app.core.db import Base, make_engine
    from app.engine.cancellation import watch_cancellation
    from app.engine.snapshot import build_problem
    from app.models.masters import CalendarException, Location, Resource, WorkerSkillMap
    from app.models.transactions import Plan, PlanAssignment, Task, WorkActual
    from app.routers.plans import router as plan_router
    from app.services.board_service import build_board
    from app.services.compare_service import compare_plans
    from app.services.demo_seed import seed_demo
    from app.services.plan_lifecycle import approve_plan, copy_plan


# 新規DBの初期データと、そのデータを使用する既存操作を確認する。
class SchemaUpdateTest(InMemoryApiTestCase):
    # 共通のメモリDBへ、月曜開始の仮データと計画APIを追加する。
    def setUp(self):
        super().setUp()
        # 同じ日付で再現できるよう、仮データの日付を固定する。
        self.seeded = seed_demo(self.db, now=datetime(2026, 11, 8, 12))
        self.app.include_router(plan_router, prefix="/api/v1")

    # Python版とSQL版の両方を空DBへ投入し、変更後の計算条件まで読み取る。
    def test_python_and_sql_seed_create_usable_plans(self):
        for mode in ("python", "sql"):
            with self.subTest(mode=mode):
                # 方式ごとに別の空DBを使い、実DBへ接続しない。
                engine = make_engine("sqlite:///:memory:")
                Base.metadata.create_all(engine)
                try:
                    with Session(engine) as db:
                        if mode == "python":
                            seed_demo(db, now=datetime(2026, 11, 8, 12))
                        else:
                            # INSERTと代表勤務行のUPDATEを取り出し、文字列のN接頭辞だけ外す。
                            sql = (Path(__file__).parents[1] / "DataBase/query/seed_demo_sqlserver.sql").read_text(encoding="utf-8")
                            for line in sql.splitlines():
                                if line.startswith(("INSERT INTO ", "UPDATE [M_Locations]")):
                                    db.execute(text(re.sub(r"\bN'", "'", line)))
                            db.commit()
                        # 製品工程とスキル設定を失わず、計算対象も21件のままになる。
                        self.assertEqual(len(list(db.scalars(select(Task)))), 21)
                        self.assertEqual(len(list(db.scalars(select(WorkerSkillMap)))), 54)
                        plans = list(db.scalars(select(Plan)))
                        self.assertEqual(len(plans), 2)
                        problem = build_problem(db, plans[0])
                        self.assertEqual(len(problem.tasks), 21)
                        self.assertEqual(len(problem.dependencies), 14)
                        self.assertTrue(all(task.options for task in problem.tasks.values()))
                        self.assertTrue(all(resource.windows for resource in problem.resources.values()))
                finally:
                    engine.dispose()

    # 個別カレンダーがなくても、拠点の停止例外が全設備へ同じように反映される。
    def test_resources_share_location_calendar_and_stops(self):
        # 全設備に共通して適用する月曜09～10時の停止。
        plan = self.db.scalar(select(Plan).order_by(Plan.PlanID))
        resource = self.db.scalar(select(Resource).where(Resource.LocationID == plan.LocationID))
        self.db.add(CalendarException(
            CalendarID=self.db.get(Location, plan.LocationID).CalendarID,
            StartAt=datetime(2026, 11, 9, 9), EndAt=datetime(2026, 11, 9, 10),
        ))
        self.db.commit()
        problem = build_problem(self.db, plan)
        windows = problem.resources[resource.ResourceID].windows
        self.assertEqual(windows[:3], [(0, 180), (240, 360), (420, 720)])
        self.assertTrue(all(item.windows == windows for item in problem.resources.values()))

    # 新しい日時項目で計画を作り、複製・比較・承認・ボード表示を続けて確認する。
    def test_plan_creation_copy_approval_and_board_use_new_dates(self):
        status, created = self.call("POST", "/plans", {
            "locationId": self.seeded["locationId"], "planName": "操作確認",
            "startAt": "2026-11-09T06:00:00+09:00", "endAt": "2026-11-12T06:00:00+09:00",
        })
        self.assertEqual(status, 201, created)
        self.assertEqual(created["startAt"], "2026-11-09T06:00:00+09:00")
        self.assertNotIn("horizonStart", created)
        # 承認に必要な割付を1件用意し、複製時にも保持する。
        plan = self.db.get(Plan, created["planId"])
        task = self.db.scalar(select(Task).order_by(Task.TaskID))
        resource = self.db.scalar(select(Resource).where(Resource.LocationID == plan.LocationID))
        self.db.add(PlanAssignment(PlanID=plan.PlanID, TaskID=task.TaskID, ResourceID=resource.ResourceID,
                                   StartAt=plan.StartAt, EndAt=datetime(2026, 11, 9, 7)))
        self.db.commit()
        copied = copy_plan(self.db, plan, "schema-test", name="操作確認コピー")
        self.assertEqual((copied.StartAt, copied.EndAt), (plan.StartAt, plan.EndAt))
        # 比較画面へ返す期間も新しい項目名に揃い、同じ日時になる。
        comparison = compare_plans(self.db, plan.PlanID, copied.PlanID)
        self.assertEqual(comparison["a"]["startAt"], "11/09 06:00")
        self.assertEqual(comparison["a"]["endAt"], comparison["b"]["endAt"])
        approve_plan(self.db, plan, "schema-test")
        self.assertEqual(plan.Status, "MASTER")
        board = build_board(self.db, plan)
        self.assertEqual(board["plan"]["startAt"], "2026-11-09T06:00:00")
        self.assertEqual(len(board["resources"]), 6)
        self.assertEqual(len(board["events"]), 1)
        self.assertTrue(all("type" not in resource for resource in board["resources"]))

    # 時間上限なしで依頼でき、重複依頼の拒否とキャンセルも維持する。
    def test_queue_and_cancel_without_time_limit(self):
        plan = self.db.scalar(select(Plan).order_by(Plan.PlanID))
        status, run = self.call("POST", f"/plans/{plan.PlanID}/solve", {"scope": "FULL"})
        self.assertEqual(status, 202, run)
        self.assertNotIn("timeLimitSec", run)
        self.assertIn("startAt", run)
        self.assertIn("endAt", run)
        self.assertEqual(self.call("POST", f"/plans/{plan.PlanID}/solve", {"scope": "FULL"})[0], 409)
        self.assertEqual(self.call("POST", f'/solver-runs/{run["runId"]}/cancel')[1]["status"], "CANCELLED")

    # 作業中・完了・中断を保存し、終了日時と状態の食い違いをDBで拒否する。
    def test_actual_end_and_status_are_stored_as_a_pair(self):
        task = self.db.scalar(select(Task).order_by(Task.TaskID))
        for state in (None, "DONE", "SUSPENDED"):
            # 作業中の終了だけ未設定にし、終了済みでは日時と状態を組にする。
            actual = WorkActual(TaskID=task.TaskID, StartAt=datetime(2026, 11, 9, 6),
                                EndAt=datetime(2026, 11, 9, 7) if state else None, Status=state)
            self.db.add(actual)
            self.db.commit()
            self.assertEqual(self.db.get(WorkActual, actual.WorkActualID).Status, state)
        for state, end in (("DONE", None), (None, datetime(2026, 11, 9, 7)), ("IN_PROGRESS", None)):
            with self.subTest(state=state, end=end):
                self.db.add(WorkActual(TaskID=task.TaskID, StartAt=datetime(2026, 11, 9, 6), EndAt=end, Status=state))
                with self.assertRaises(IntegrityError):
                    self.db.commit()
                self.db.rollback()


# 計算ライブラリに依存せず、解の更新がない状況の中止監視を確認する。
class CancellationWatchTest(unittest.TestCase):
    # 中止要求を検知した際に停止処理を呼び、完了合図で監視も終了する。
    def test_cancellation_is_detected_without_solution_updates(self):
        # 監視終了と停止呼出しを別々の合図で受け取り、待機時間を限定する。
        finished, stopped = Event(), Event()
        watcher = Thread(target=watch_cancellation, args=(stopped.set, finished, lambda: True), daemon=True)
        watcher.start()
        try:
            self.assertTrue(stopped.wait(2))
        finally:
            finished.set()
            watcher.join(2)
        self.assertFalse(watcher.is_alive())

    # 通常の計算完了では、中止処理を呼ばずに監視を終了する。
    def test_finished_calculation_does_not_call_stop(self):
        finished = Event()
        finished.set()
        stop = Mock()
        watch_cancellation(stop, finished, lambda: True)
        stop.assert_not_called()

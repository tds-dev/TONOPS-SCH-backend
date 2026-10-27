"""エンジンテスト用の小さな手組み問題（DB なし）。"""
from datetime import datetime

from app.engine.problem import (
    PChangeover,
    PDependency,
    PJob,
    POption,
    PResource,
    Problem,
    PRule,
    PTask,
)

# 2026-10-27（火）06:00 JST
START = datetime(2026, 10, 26, 21, 0)
DAY = 24 * 60


def two_machine_problem(**overrides) -> Problem:
    """配合機 2 台（2 日間、各日 06:00–12:00, 13:00–22:00）、2 タスクのジョブ 4 件。

    タスク 1x = 配合（どちらの配合機でも可）、タスク 2x = 包装機での包装（配合の 30 分後）。
    系統: ジョブ1 A、ジョブ2 B、ジョブ3 A、ジョブ4 C。
    """
    windows = []
    for d in range(2):
        windows += [(d * DAY, d * DAY + 360), (d * DAY + 420, d * DAY + 960)]
    resources = {
        1: PResource(1, "M-01", "配合機 M-01", 1, windows, group_id=10),
        2: PResource(2, "M-02", "配合機 M-02", 1, windows, group_id=10),
        3: PResource(3, "P-01", "包装機 P-01", 1, windows, group_id=20),
    }
    fams = {1: "A", 2: "B", 3: "A", 4: "C"}
    jobs, tasks, deps = {}, {}, []
    for j in range(1, 5):
        jobs[j] = PJob(j, f"JB-{j}", due=600 + 120 * j, priority=50)
        mix, pack = 10 + j, 20 + j
        tasks[mix] = PTask(mix, j, f"JB-{j} 配合", {"family": fams[j]},
                           [POption(1, 90), POption(2, 90)])
        tasks[pack] = PTask(pack, j, f"JB-{j} 包装", {"family": fams[j]}, [POption(3, 60)])
        deps.append(PDependency(mix, pack, "FS", 30))
    changeovers = [PChangeover(
        1, "family", {1, 2}, default=0,
        entries={("A", "B"): (30, False), ("B", "A"): (0, True), ("A", "C"): (45, False),
                 ("C", "A"): (120, False), ("B", "C"): (30, False), ("C", "B"): (60, False)},
    )]
    p = Problem(
        horizon_start=START, horizon=2 * DAY, tz="Asia/Tokyo", resources=resources, tasks=tasks,
        jobs=jobs, dependencies=deps, changeovers=changeovers, rules=[],
        weights={"lateness": 1000, "unscheduled": 100000, "setup": 10, "makespan": 1}, time_limit_sec=10,
    )
    for k, v in overrides.items():
        setattr(p, k, v)
    return p


def weekday_rule(weekdays: list[int], family: str = "C") -> PRule:
    return PRule(99, "allowed_weekdays", "曜日制限", {"family": family}, {"weekdays": weekdays}, True, 100)

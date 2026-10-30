"""スケジュールのチェッカーと KPI（純粋 Python、OR-Tools 不要）。"""
from app.engine.evaluate import SAssignment, check_schedule, compute_kpis
from app.engine.problem import matches
from tests.engine_fixtures import two_machine_problem, weekday_rule


def codes(violations, severity=None):
    return sorted(v.code for v in violations if severity is None or v.severity == severity)


def good_schedule():
    # M-01: A(オーダー1) 0–90, A(オーダー3) 90–180 ; M-02: B(オーダー2) 0–90, C(オーダー4) 120–210
    # P-01: 各配合の 30 分後に 1 件ずつ包装
    return [
        SAssignment(11, 1, 0, 90), SAssignment(13, 1, 90, 180),
        SAssignment(12, 2, 0, 90), SAssignment(14, 2, 120, 210, setup=30),
        SAssignment(21, 3, 120, 180), SAssignment(22, 3, 180, 240),
        SAssignment(23, 3, 240, 300), SAssignment(24, 3, 420, 480),
    ]


def test_valid_schedule_has_no_hard_violations():
    p = two_machine_problem()
    assert codes(check_schedule(p, good_schedule()), "HARD") == []


def test_detects_overlap_calendar_dependency_and_unscheduled():
    p = two_machine_problem()
    sched = good_schedule()
    sched[1] = SAssignment(13, 1, 60, 150)  # M-01 でオーダー1 と重なる
    sched[7] = SAssignment(24, 3, 330, 390)  # 12:00–13:00 の休憩をまたぐ
    sched[4] = SAssignment(21, 3, 100, 160)  # 配合の 10 分後しかない（30 分必要）
    del sched[5]  # オーダー2 の包装が未割付
    got = codes(check_schedule(p, sched), "HARD")
    assert "OVERLAP" in got and "OUTSIDE_CALENDAR" in got and "DEPENDENCY" in got and "UNSCHEDULED" in got


def test_forbidden_and_short_changeovers():
    p = two_machine_problem()
    sched = good_schedule()
    # M-02 で B→A は禁止。A→C は 45 分必要
    sched[2] = SAssignment(12, 2, 0, 90)
    sched[0] = SAssignment(11, 2, 100, 190)
    sched[3] = SAssignment(14, 1, 200, 290)
    sched[1] = SAssignment(13, 1, 100, 190)
    got = codes(check_schedule(p, sched), "HARD")
    assert "FORBIDDEN_SEQUENCE" in got
    assert "SETUP_TOO_SHORT" in got  # M-01 で A(13) は 190 に終了、C(14) は 200 に開始


def test_weekday_rule_check():
    # 計画期間は火曜開始。系統C の火曜を禁止
    p = two_machine_problem(rules=[weekday_rule([3, 4, 5])])
    got = check_schedule(p, good_schedule())
    assert "WEEKDAY" in codes(got, "HARD")


def test_kpis_and_late_orders():
    p = two_machine_problem()
    p.orders[1].due = 150  # オーダー1 は 180 に完了 -> 30 分遅れ
    sched = good_schedule()
    kpi = compute_kpis(p, sched)
    assert kpi["late_orders"] == 1 and kpi["total_lateness_min"] == 30
    assert kpi["setup_min"] == 30 and kpi["scheduled_tasks"] == 8 and kpi["makespan_min"] == 480
    late = [v for v in check_schedule(p, sched) if v.code == "LATE_ORDER"]
    assert late and late[0].message.startswith("JB-1 が30分遅れ")


def test_selector_matching():
    attrs = {"family": "A", "packing": "bulk"}
    assert matches({}, attrs)
    assert matches({"family": "A"}, attrs)
    assert matches({"family": {"in": ["A", "B"]}}, attrs)
    assert not matches({"family": {"notIn": ["A"]}}, attrs)
    assert not matches({"family": "A", "packing": "bag"}, attrs)


def test_local_days_cover_horizon():
    p = two_machine_problem()
    days = p.local_days()
    assert [d.isoweekday() for d, _, _ in days] == [2, 3, 4]  # 火 06:00 → 木 06:00
    assert days[0][1] == 0 and days[-1][2] == p.horizon

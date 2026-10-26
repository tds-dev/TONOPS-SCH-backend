"""Schedule checker and KPIs (pure Python, no OR-Tools)."""
from app.engine.evaluate import SAssignment, check_schedule, compute_kpis
from app.engine.problem import matches
from tests.engine_fixtures import two_machine_problem, weekday_rule


def codes(violations, severity=None):
    return sorted(v.code for v in violations if severity is None or v.severity == severity)


def good_schedule():
    # M-01: A(job1) 0–90, A(job3) 90–180 ; M-02: B(job2) 0–90, C(job4) 120–210
    # P-01: packs 30 min after each mix, one at a time
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
    sched[1] = SAssignment(13, 1, 60, 150)  # overlaps job1 on M-01
    sched[7] = SAssignment(24, 3, 330, 390)  # crosses the 12:00–13:00 break
    sched[4] = SAssignment(21, 3, 100, 160)  # only 10 min after mixing (needs 30)
    del sched[5]  # job2 packing unscheduled
    got = codes(check_schedule(p, sched), "HARD")
    assert "OVERLAP" in got and "OUTSIDE_CALENDAR" in got and "DEPENDENCY" in got and "UNSCHEDULED" in got


def test_forbidden_and_short_changeovers():
    p = two_machine_problem()
    sched = good_schedule()
    # B then A on M-02 is forbidden; A then C needs 45 min
    sched[2] = SAssignment(12, 2, 0, 90)
    sched[0] = SAssignment(11, 2, 100, 190)
    sched[3] = SAssignment(14, 1, 200, 290)
    sched[1] = SAssignment(13, 1, 100, 190)
    got = codes(check_schedule(p, sched), "HARD")
    assert "FORBIDDEN_SEQUENCE" in got
    assert "SETUP_TOO_SHORT" in got  # A(13) ends 190, C(14) starts 200 on M-01


def test_weekday_rule_check():
    # Horizon starts Tuesday; forbid Tuesday for family C
    p = two_machine_problem(rules=[weekday_rule([3, 4, 5])])
    got = check_schedule(p, good_schedule())
    assert "WEEKDAY" in codes(got, "HARD")


def test_kpis_and_late_jobs():
    p = two_machine_problem()
    p.jobs[1].due = 150  # job 1 finishes at 180 -> 30 min late
    sched = good_schedule()
    kpi = compute_kpis(p, sched)
    assert kpi["late_jobs"] == 1 and kpi["total_lateness_min"] == 30
    assert kpi["setup_min"] == 30 and kpi["scheduled_tasks"] == 8 and kpi["makespan_min"] == 480
    late = [v for v in check_schedule(p, sched) if v.code == "LATE_JOB"]
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
    assert [d.isoweekday() for d, _, _ in days] == [2, 3, 4]  # Tue 06:00 → Thu 06:00
    assert days[0][1] == 0 and days[-1][2] == p.horizon

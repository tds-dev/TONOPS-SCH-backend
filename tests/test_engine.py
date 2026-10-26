"""CP-SAT model tests. Every solution is cross-checked with the pure checker,
so the model and the checker cannot silently disagree."""
import pytest

pytest.importorskip("ortools")

from app.engine.evaluate import check_schedule  # noqa: E402
from app.engine.model_builder import solve_problem  # noqa: E402
from app.engine.problem import PLock, POption  # noqa: E402
from tests.engine_fixtures import two_machine_problem, weekday_rule  # noqa: E402


def hard(problem, result):
    return [v for v in check_schedule(problem, result.assignments) if v.severity == "HARD"]


def test_all_tasks_scheduled_without_hard_violations():
    p = two_machine_problem()
    r = solve_problem(p, time_limit_sec=10)
    assert r.status in ("OPTIMAL", "FEASIBLE")
    assert len(r.assignments) == 8
    assert hard(p, r) == []


def test_changeover_setup_is_recorded_and_forbidden_order_avoided():
    p = two_machine_problem()
    # Only one mixer: all four mixing tasks share it, so sequence matters
    for t in p.tasks.values():
        t.options = [o for o in t.options if o.resource_id != 2]
    r = solve_problem(p, time_limit_sec=10)
    assert hard(p, r) == []
    mixes = sorted((a for a in r.assignments if a.resource_id == 1), key=lambda a: a.start)
    fams = [p.tasks[a.task_id].attrs["family"] for a in mixes]
    for prev, cur in zip(fams, fams[1:], strict=False):
        assert (prev, cur) != ("B", "A")
    # setups recorded on the assignments equal what the matrix requires
    for prev_a, cur_a in zip(mixes, mixes[1:], strict=False):
        need, _ = p.changeovers[0].lookup(p.tasks[prev_a.task_id].attrs["family"], p.tasks[cur_a.task_id].attrs["family"])
        assert cur_a.setup == need


def test_locked_task_stays_put():
    p = two_machine_problem()
    p.tasks[11].lock = PLock(resource_id=2, start=420, end=510)
    r = solve_problem(p, time_limit_sec=10)
    a = next(x for x in r.assignments if x.task_id == 11)
    assert (a.resource_id, a.start, a.end, a.locked) == (2, 420, 510, True)
    assert hard(p, r) == []


def test_weekday_rule_moves_family_c_off_tuesday():
    p = two_machine_problem(rules=[weekday_rule([3, 4, 5])])  # C only Wed–Fri
    r = solve_problem(p, time_limit_sec=10)
    assert hard(p, r) == []
    for a in r.assignments:
        if p.tasks[a.task_id].attrs["family"] == "C":
            assert a.start >= 18 * 60  # Wednesday 00:00 JST is 18 h after Tue 06:00


def test_task_too_long_for_any_window_is_left_unscheduled():
    p = two_machine_problem()
    p.tasks[11].options = [POption(1, 600), POption(2, 600)]  # longest window is 540 min
    r = solve_problem(p, time_limit_sec=10)
    scheduled = {a.task_id for a in r.assignments}
    assert 11 not in scheduled and 21 not in scheduled  # its successor cannot run either
    assert {v.code for v in check_schedule(p, r.assignments)} >= {"UNSCHEDULED"}


def test_lateness_is_minimised_for_high_priority_job():
    p = two_machine_problem()
    for j in p.jobs.values():
        j.due = 200  # everyone wants to finish by 09:20
    p.jobs[4].priority = 1
    r = solve_problem(p, time_limit_sec=10)
    finish = {}
    for a in r.assignments:
        job = p.tasks[a.task_id].job_id
        finish[job] = max(finish.get(job, 0), a.end)
    assert finish[4] == min(finish.values())

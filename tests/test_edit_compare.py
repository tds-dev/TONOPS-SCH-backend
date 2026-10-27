"""手動編集と計画比較（純粋関数、OR-Tools 不要）。"""
from datetime import datetime, timedelta

from app.engine.compare import Slot, assignment_diff, kpi_deltas
from app.engine.edit import Change, apply_changes, new_violations, recompute_setups
from tests.engine_fixtures import two_machine_problem
from tests.test_evaluate import good_schedule


def by_task(items):
    return {a.task_id: a for a in items}


def test_move_keeps_duration_and_locks_by_default():
    p = two_machine_problem()
    after, affected, changed, errors = apply_changes(p, good_schedule(), [Change(24, start=480)])
    assert errors == [] and changed == {24} and affected == {3}
    a = by_task(after)[24]
    assert (a.start, a.end, a.locked) == (480, 540, True)


def test_move_to_other_resource_uses_its_duration_and_recomputes_setups():
    p = two_machine_problem()
    p.tasks[13].options[1].duration = 120  # M-02 では 120 分
    # ジョブ3（A）を M-01 から M-02 の C の後ろへ
    after, affected, _, errors = apply_changes(p, good_schedule(), [Change(13, resource_id=2, start=330)])
    assert errors == [] and affected == {1, 2}
    a = by_task(after)[13]
    assert (a.resource_id, a.start, a.end) == (2, 330, 450)
    assert a.setup == 120  # C→A の段取り
    assert by_task(after)[14].setup == 30  # B→C はそのまま


def test_locked_task_cannot_move_without_unlock():
    p = two_machine_problem()
    sched = good_schedule()
    sched[0].locked = True  # タスク11
    _, _, _, errors = apply_changes(p, sched, [Change(11, start=30)])
    assert errors and "ロック" in errors[0]
    after, _, _, errors = apply_changes(p, sched, [Change(11, start=30, lock=False)])
    assert errors == [] and by_task(after)[11].locked is False


def test_place_unscheduled_task_and_remove():
    p = two_machine_problem()
    sched = [a for a in good_schedule() if a.task_id != 24]
    after, _, changed, errors = apply_changes(p, sched, [Change(24, resource_id=3, start=420)])
    assert errors == [] and changed == {24} and by_task(after)[24].end == 480
    after, _, _, errors = apply_changes(p, after, [Change(24, remove=True, lock=False)])
    assert errors == [] and 24 not in by_task(after)
    _, _, _, errors = apply_changes(p, sched, [Change(24, resource_id=1, start=420)])
    assert errors and "実行できません" in errors[0]


def test_new_violations_only_reports_what_the_change_caused():
    p = two_machine_problem()
    before = [a for a in good_schedule() if a.task_id != 24]  # 既存の違反: 24 が未割付
    after, _, _, _ = apply_changes(p, before, [Change(22, start=120)])  # 21 (120–180) と重なる
    codes = [v.code for v in new_violations(p, before, after)]
    assert "OVERLAP" in codes
    assert "UNSCHEDULED" not in codes  # 変更前からある違反は含めない


def test_recompute_setups_first_task_has_none():
    p = two_machine_problem()
    sched = good_schedule()
    for a in sched:
        a.setup = 99
    recompute_setups(p, sched, {2})
    m2 = sorted((a for a in sched if a.resource_id == 2), key=lambda a: a.start)
    assert [a.setup for a in m2] == [0, 30]


def test_kpi_deltas_direction():
    rows = {d.key: d for d in kpi_deltas(
        {"late_jobs": 2, "setup_min": 220, "utilisation_pct": 78},
        {"late_jobs": 0, "setup_min": 250, "utilisation_pct": 80},
    )}
    assert rows["late_jobs"].delta == -2 and rows["late_jobs"].better is True
    assert rows["setup_min"].better is False
    assert rows["utilisation_pct"].better is True
    assert list(rows) == ["late_jobs", "setup_min", "utilisation_pct"]


def test_assignment_diff_kinds():
    t0 = datetime(2026, 10, 27, 6)
    h = lambda n: t0 + timedelta(hours=n)  # noqa: E731
    a = {1: Slot(1, h(0), h(2)), 2: Slot(1, h(2), h(4)), 3: Slot(2, h(0), h(1)), 5: Slot(1, h(5), h(6))}
    b = {1: Slot(1, h(0), h(2)), 2: Slot(1, h(3), h(5)), 3: Slot(1, h(0), h(1)), 4: Slot(2, h(1), h(2))}
    kinds = {c.task_id: (c.kind, c.shift_minutes) for c in assignment_diff(a, b)}
    assert kinds == {2: ("MOVED", 60), 3: ("RESOURCE", 0), 4: ("ADDED", None), 5: ("REMOVED", None)}

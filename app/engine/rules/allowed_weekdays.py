"""allowed_weekdays: matching tasks may only run on the listed weekdays
(site local time, 1 = Mon ... 7 = Sun). Hard rule.

Example (M_Rules): SelectorJSON {"family": "C"}, ParamsJSON {"weekdays": [1,2,3,4,5]}
→ family C is never produced on Saturday or Sunday.
"""
from app.engine.problem import Problem, PRule, matches
from app.engine.result import SAssignment, Violation, fmt
from app.engine.rules import RulePlugin, register

DAY_NAMES = "月火水木金土日"


def blocked_ranges(problem: Problem, weekdays: list[int]) -> list[tuple[int, int]]:
    allowed = set(weekdays)
    return [(s, e) for day, s, e in problem.local_days() if day.isoweekday() not in allowed]


@register
class AllowedWeekdays(RulePlugin):
    type_key = "allowed_weekdays"
    label = "生産可能曜日"
    description = "対象タスクを指定した曜日のみに実行します。"
    params_schema = {
        "type": "object",
        "required": ["weekdays"],
        "properties": {
            "weekdays": {
                "type": "array",
                "items": {"type": "integer", "minimum": 1, "maximum": 7},
                "title": "曜日（1=月 … 7=日）",
            }
        },
    }

    def apply(self, ctx, rule: PRule) -> None:
        blocked = blocked_ranges(ctx.problem, rule.params.get("weekdays", []))
        if not blocked:
            return
        model = ctx.model
        fixed = [model.NewIntervalVar(s, e - s, e, f"blk_r{rule.id}_{s}") for s, e in blocked]
        for task in ctx.problem.tasks.values():
            if task.lock is None and matches(rule.selector, task.attrs):
                model.AddNoOverlap([ctx.task_vars[task.id].interval, *fixed])

    def check(self, problem: Problem, rule: PRule, assignments: list[SAssignment]) -> list[Violation]:
        blocked = blocked_ranges(problem, rule.params.get("weekdays", []))
        out = []
        for a in assignments:
            t = problem.tasks.get(a.task_id)
            if t is None or a.locked or not matches(rule.selector, t.attrs):
                continue
            if any(a.start < e and s < a.end for s, e in blocked):
                allowed = "".join(DAY_NAMES[d - 1] for d in sorted(rule.params.get("weekdays", [])))
                out.append(Violation(
                    "HARD" if rule.hard else "SOFT", "WEEKDAY",
                    f"ルール「{rule.name}」: {t.name} は {allowed} のみ実行可能です（{fmt(problem, a.start)}）",
                    task_id=t.id, rule_id=rule.id,
                ))
        return out

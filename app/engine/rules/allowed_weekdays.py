"""allowed_weekdays: 対象タスクは指定した曜日にのみ実行できる
（拠点の現地時間、1 = 月 … 7 = 日）。必須ルール。

例（M_Rules）: SelectorJSON {"family": "C"}, ParamsJSON {"weekdays": [1,2,3,4,5]}
→ 系統C は土曜・日曜に生産しない。
"""
from app.engine.problem import Problem, PRule, matches
from app.engine.result import SAssignment, Violation, fmt
from app.engine.rules import RulePlugin, register

# 許可曜日を画面に表示するための、月曜から日曜までの文字列。
DAY_NAMES = "月火水木金土日"


# 許可されていない曜日の時間帯を、計画開始からの分数で返す。
def blocked_ranges(problem: Problem, weekdays: list[int]) -> list[tuple[int, int]]:
    allowed = set(weekdays)
    return [(s, e) for day, s, e in problem.local_days() if day.isoweekday() not in allowed]


@register
class AllowedWeekdays(RulePlugin):
    # ルールの識別名・画面の表示名・説明と、曜日入力の仕様。
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

    # 対象タスクと禁止曜日の時間帯が重ならない制約を計算へ追加する。
    def apply(self, ctx, rule: PRule) -> None:
        blocked = blocked_ranges(ctx.problem, rule.params.get("weekdays", []))
        if not blocked:
            return
        model = ctx.model
        fixed = [model.NewIntervalVar(s, e - s, e, f"blk_r{rule.id}_{s}") for s, e in blocked]
        for task in ctx.problem.tasks.values():
            if task.lock is None and matches(rule.selector, task.attrs):
                model.AddNoOverlap([ctx.task_vars[task.id].interval, *fixed])

    # 禁止曜日に割り付けられたタスクを調べ、画面へ返す違反を作成する。
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

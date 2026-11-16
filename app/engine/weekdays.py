"""製品工程の許可曜日を、自動計算と手動編集の違反検証へ共通適用する処理。"""
from app.core.timeutil import weekday_number
from app.engine.problem import Problem
from app.engine.result import SAssignment, Violation, fmt

# 曜日番号と一致する、日曜から土曜までの表示名。
DAY_NAMES = "日月火水木金土"


# 計画期間のうち、許可されない曜日に属する時間帯を分数で返す。
def blocked_ranges(problem: Problem, weekdays: list[int]) -> list[tuple[int, int]]:
    # 同じ曜日を繰り返し検索しないよう、許可曜日を集合へまとめる。
    allowed = set(weekdays)
    return [(start, end) for day, start, end in problem.local_days() if weekday_number(day) not in allowed]


# 工程の許可曜日外へ作業時間が重ならない制約を、自動計算へ追加する。
def apply_weekday_restrictions(ctx) -> None:
    # 同じ許可曜日の工程では、禁止時間帯の計算と固定区間を共用する。
    intervals = {}
    for task in ctx.problem.tasks.values():
        if task.lock is not None or task.allowed_weekdays is None:
            continue
        # 並び順の異なる同一設定も、同じ禁止区間を参照する。
        key = tuple(sorted(task.allowed_weekdays))
        if key not in intervals:
            intervals[key] = [ctx.model.NewIntervalVar(start, end - start, end, f"weekday_{key}_{start}")
                              for start, end in blocked_ranges(ctx.problem, list(key))]
        if intervals[key]:
            ctx.model.AddNoOverlap([ctx.task_vars[task.id].interval, *intervals[key]])


# 禁止曜日に重なった割付を、工程に紐づく必須違反として返す。
def check_weekday_restrictions(problem: Problem, assignments: list[SAssignment]) -> list[Violation]:
    # 同じ許可曜日の禁止区間を一度だけ作り、全割付の検証で使う。
    ranges = {}
    violations = []
    for assignment in assignments:
        task = problem.tasks.get(assignment.task_id)
        if task is None or assignment.locked or task.allowed_weekdays is None:
            continue
        key = tuple(sorted(task.allowed_weekdays))
        if key not in ranges:
            ranges[key] = blocked_ranges(problem, list(key))
        if any(assignment.start < end and start < assignment.end for start, end in ranges[key]):
            # 曜日名と開始日時を添え、既存の課題一覧で修正対象を確認できるようにする。
            allowed = "".join(DAY_NAMES[day] for day in key)
            violations.append(Violation(
                "HARD", "WEEKDAY",
                f"工程の曜日制限: {task.name} は {allowed} のみ実行可能です（{fmt(problem, assignment.start)}）",
                task_id=task.id,
            ))
    return violations

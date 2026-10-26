"""Load everything a solve needs from the database into a `Problem`.

What is included:
  * resources of the plan's site (not deleted) with working windows from
    their calendar (or the site default calendar)
  * jobs of the site that are not DONE / CANCELLED, owned by the scheduler and
    released before the horizon end; their non-summary, unfinished tasks
  * resource options (group options expanded to each member resource)
  * dependencies between included tasks
  * locks: locked assignments of this plan and of its base plan, plus base-plan
    work that starts inside the frozen window
  * hints: all other assignments of this plan (or the base plan) for warm start
  * active changeover matrices and rules of the site
"""
from sqlalchemy import false, or_, select
from sqlalchemy.orm import Session

from app.core.timeutil import utc_to_local
from app.engine.problem import (
    PChangeover,
    PDependency,
    PJob,
    PLock,
    POption,
    PResource,
    Problem,
    PRule,
    PTask,
)
from app.models.masters import ChangeoverMatrix, PlanProfile, Resource, Rule, Site
from app.models.transactions import Job, Plan, PlanAssignment, Task, TaskDependency
from app.services.calendar_service import working_time
from app.services.worktime import Interval


def _windows(intervals: list[Interval], problem_start, horizon: int) -> list[tuple[int, int]]:
    out = []
    for s, e in intervals:
        a = int((s - problem_start).total_seconds() // 60)
        b = int((e - problem_start).total_seconds() // 60)
        a, b = max(0, a), min(horizon, b)
        if b > a:
            out.append((a, b))
    return out


def build_problem(db: Session, plan: Plan, scope: str = "FULL") -> Problem:
    site = db.get(Site, plan.SiteID)
    profile = db.get(PlanProfile, plan.ProfileID)
    tz = site.TimeZone
    start, end = plan.HorizonStart, plan.HorizonEnd
    horizon = int((end - start).total_seconds() // 60)
    to_min = lambda dt: int((dt - start).total_seconds() // 60)  # noqa: E731

    weights = dict(profile.ObjectiveWeightsJSON or {}) if profile else {}
    if scope == "REPAIR":
        weights.setdefault("stability", 20)

    # ---- resources and calendars
    resources: dict[int, PResource] = {}
    rows = db.scalars(
        select(Resource).where(Resource.SiteID == site.SiteID, Resource.DeleteFlag.is_(False))
    ).all()
    calendar_cache: dict[int, list[tuple[int, int]]] = {}
    for r in rows:
        cal_id = r.CalendarID or site.DefaultCalendarID
        if cal_id is None:
            windows = [(0, horizon)]  # no calendar: always available
        else:
            if cal_id not in calendar_cache:
                calendar_cache[cal_id] = _windows(working_time(db, cal_id, start, end, tz), start, horizon)
            windows = calendar_cache[cal_id]
        resources[r.ResourceID] = PResource(
            id=r.ResourceID, code=r.ResourceCode, name=r.ResourceName,
            capacity=max(1, int(r.Capacity or 1)), windows=windows, group_id=r.ResourceGroupID,
        )
    members: dict[int, list[int]] = {}
    for r in rows:
        if r.ResourceGroupID:
            members.setdefault(r.ResourceGroupID, []).append(r.ResourceID)

    # ---- jobs and tasks
    jobs_rows = db.scalars(
        select(Job).where(
            Job.SiteID == site.SiteID,
            Job.DeleteFlag.is_(False),
            Job.Status.notin_(["DONE", "CANCELLED"]),
            Job.PlanOwner == "SCHEDULER",
            or_(Job.ReleaseAt.is_(None), Job.ReleaseAt < end),
        )
    ).all()
    jobs = {
        j.JobID: PJob(id=j.JobID, no=j.JobNo, due=to_min(j.DueAt) if j.DueAt else None, priority=j.Priority)
        for j in jobs_rows
    }
    job_release = {j.JobID: max(0, to_min(j.ReleaseAt)) if j.ReleaseAt else 0 for j in jobs_rows}
    task_rows = db.scalars(
        select(Task).where(
            Task.JobID.in_(list(jobs)) if jobs else false(),
            Task.IsSummary.is_(False),
            Task.Status.notin_(["DONE", "CANCELLED"]),
        )
    ).all()

    # ---- previous positions: this plan first, else the base plan
    def assignments_of(plan_id: int | None) -> dict[int, PlanAssignment]:
        if plan_id is None:
            return {}
        return {a.TaskID: a for a in db.scalars(select(PlanAssignment).where(PlanAssignment.PlanID == plan_id))}

    own = assignments_of(plan.PlanID)
    base = assignments_of(plan.BasePlanID)
    frozen_end = (profile.FrozenWindowHours if profile else 0) * 60

    tasks: dict[int, PTask] = {}
    for t in task_rows:
        options: list[POption] = []
        for o in t.options:
            targets = [o.ResourceID] if o.ResourceID else members.get(o.ResourceGroupID, [])
            options.extend(POption(rid, int(o.DurationMin), int(o.Priority or 1)) for rid in targets if rid in resources)
        release = job_release.get(t.JobID, 0)
        if t.EarliestStartAt:
            release = max(release, to_min(t.EarliestStartAt))
        release = max(release, frozen_end)  # nothing new starts inside the frozen window
        task = PTask(
            id=t.TaskID, job_id=t.JobID, name=f"{jobs[t.JobID].no} {t.TaskName}",
            attrs=dict(t.AttributesJSON or {}), options=options, release=release,
            deadline=to_min(t.DeadlineAt) if t.DeadlineAt else None,
        )
        prev = own.get(t.TaskID) or base.get(t.TaskID)
        if prev is not None:
            pos = PLock(prev.ResourceID, to_min(prev.StartAt), to_min(prev.EndAt))
            frozen = prev is base.get(t.TaskID) and pos.start < frozen_end
            if (prev.IsLocked or frozen) and pos.end > 0 and pos.end > pos.start:
                task.lock = pos
            elif 0 <= pos.start < horizon:
                task.hint = pos
        tasks[t.TaskID] = task

    deps = [
        PDependency(d.PredecessorTaskID, d.SuccessorTaskID, d.DependencyType, int(d.LagMin or 0),
                    int(d.MaxLagMin) if d.MaxLagMin is not None else None)
        for d in db.scalars(
            select(TaskDependency).where(
                TaskDependency.SuccessorTaskID.in_(list(tasks)) if tasks else false()
            )
        )
        if d.PredecessorTaskID in tasks
    ]

    # ---- changeovers and rules
    changeovers = []
    for mx in db.scalars(
        select(ChangeoverMatrix).where(ChangeoverMatrix.SiteID == site.SiteID, ChangeoverMatrix.IsActive.is_(True))
    ):
        rids = set(members.get(mx.ResourceGroupID, [])) if mx.ResourceGroupID else set(resources)
        changeovers.append(PChangeover(
            id=mx.MatrixID, attribute=mx.AttributeKey, resource_ids=rids, default=int(mx.DefaultMinutes or 0),
            entries={(e.FromValue, e.ToValue): (int(e.SetupMinutes or 0), bool(e.IsForbidden)) for e in mx.entries},
        ))
    plan_day = utc_to_local(start, tz).date()  # rule validity is checked on the local start date
    rules = [
        PRule(r.RuleID, r.RuleTypeKey, r.RuleName, dict(r.SelectorJSON or {}), dict(r.ParamsJSON or {}),
              bool(r.IsHard), int(r.Weight or 100))
        for r in db.scalars(select(Rule).where(Rule.SiteID == site.SiteID, Rule.IsActive.is_(True)))
        if (r.ValidFrom is None or r.ValidFrom <= plan_day) and (r.ValidTo is None or r.ValidTo >= plan_day)
    ]

    return Problem(
        horizon_start=start, horizon=horizon, tz=tz, resources=resources, tasks=tasks, jobs=jobs,
        dependencies=deps, changeovers=changeovers, rules=rules, weights=weights,
        time_limit_sec=profile.TimeLimitSec if profile else 60,
    )

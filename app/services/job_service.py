"""Turning a job into schedulable tasks.

`generate_tasks` expands the job's routing (or its item's default routing)
into T_Tasks, T_TaskResourceOptions and FS dependencies between consecutive
steps. Task attributes = item attributes, overridden by step, then job
attributes, so rule selectors such as {"family": "A"} work on tasks.
"""
import math

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.masters import Item, Routing
from app.models.transactions import Job, PlanAssignment, Task, TaskDependency, TaskResourceOption


def option_duration(setup: int, fixed: int, minutes_per_unit: float, quantity: float) -> int:
    """Duration in whole minutes = setup + fixed + quantity × minutes per unit."""
    return int(setup + fixed + math.ceil(float(quantity or 0) * float(minutes_per_unit or 0)))


def resolve_routing(db: Session, job: Job) -> Routing:
    if job.RoutingID:
        routing = db.get(Routing, job.RoutingID)
    elif job.ItemID:
        routing = db.scalars(
            select(Routing)
            .where(Routing.ItemID == job.ItemID, Routing.DeleteFlag.is_(False))
            .order_by(Routing.IsDefault.desc(), Routing.Revision.desc())
        ).first()
    else:
        routing = None
    if routing is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Job {job.JobNo} has no routing (set RoutingID or an item with a routing).",
        )
    return routing


def generate_tasks(db: Session, job: Job, user: str, replace: bool = False) -> list[Task]:
    existing = db.scalars(select(Task).where(Task.JobID == job.JobID)).all()
    if existing:
        if not replace:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"Job {job.JobNo} already has {len(existing)} tasks; pass replace=true to rebuild.",
            )
        task_ids = [t.TaskID for t in existing]
        used = db.scalars(
            select(PlanAssignment.TaskID).where(PlanAssignment.TaskID.in_(task_ids)).limit(1)
        ).first()
        if used is not None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"Job {job.JobNo} tasks are used in a plan; they cannot be rebuilt.",
            )
        db.execute(
            delete(TaskDependency).where(
                TaskDependency.PredecessorTaskID.in_(task_ids)
                | TaskDependency.SuccessorTaskID.in_(task_ids)
            )
        )
        for t in existing:
            db.delete(t)
        db.flush()

    routing = resolve_routing(db, job)
    item = db.get(Item, routing.ItemID)
    base_attrs = dict(item.AttributesJSON or {}) if item else {}
    qty = float(job.Quantity or 0)

    tasks: list[Task] = []
    for seq, step in enumerate(routing.steps, start=1):
        attrs = {**base_attrs, **(step.AttributesJSON or {}), **(job.AttributesJSON or {})}
        task = Task(
            JobID=job.JobID,
            RoutingStepID=step.RoutingStepID,
            TaskNo=str(step.StepNo),
            TaskName=step.StepName,
            Sequence=seq,
            Status="NOT_STARTED",
            AttributesJSON=attrs,
            CreatedBy=user,
        )
        for sr in step.resources:
            task.options.append(
                TaskResourceOption(
                    ResourceID=sr.ResourceID,
                    ResourceGroupID=sr.ResourceGroupID,
                    DurationMin=option_duration(
                        sr.SetupMinutes, sr.FixedMinutes, sr.MinutesPerUnit, qty
                    ),
                    SetupMinutes=sr.SetupMinutes,
                    Priority=sr.Priority,
                    CreatedBy=user,
                )
            )
        db.add(task)
        tasks.append(task)
    db.flush()

    steps = list(routing.steps)
    for i in range(1, len(tasks)):
        prev_step = steps[i - 1]
        db.add(
            TaskDependency(
                PredecessorTaskID=tasks[i - 1].TaskID,
                SuccessorTaskID=tasks[i].TaskID,
                DependencyType="FS",
                LagMin=prev_step.MinLagAfterMin or 0,
                MaxLagMin=prev_step.MaxLagAfterMin,
                CreatedBy=user,
            )
        )
    if job.RoutingID is None:
        job.RoutingID = routing.RoutingID
    db.commit()
    for t in tasks:
        db.refresh(t)
    return tasks

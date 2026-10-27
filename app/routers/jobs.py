"""ジョブ、タスク、依存関係。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.transactions import Job, Task, TaskDependency, TaskResourceOption
from app.routers.crud import crud_router
from app.routers.deps import current_user
from app.schemas.base import schemas_for
from app.services.job_service import generate_tasks

TaskRead, _, _ = schemas_for(Task)
OptionRead, _, _ = schemas_for(TaskResourceOption)
DependencyRead, _, _ = schemas_for(TaskDependency)


class TaskWithOptions(TaskRead):  # type: ignore[misc, valid-type]
    options: list[OptionRead] = []  # type: ignore[valid-type]


job_extra = APIRouter(prefix="/jobs", tags=["Jobs"])


@job_extra.post("/{job_id}/generate-tasks", response_model=list[TaskWithOptions])
def post_generate_tasks(
    job_id: int,
    replace: bool = False,
    db: Session = Depends(get_db),
    user: str = Depends(current_user),
):
    """ジョブの工程ルートを展開し、タスク・リソース候補・依存関係を作成する。"""
    job = db.get(Job, job_id)
    if job is None or job.DeleteFlag:
        raise HTTPException(404, f"Job {job_id} not found")
    return generate_tasks(db, job, user, replace=replace)


@job_extra.get("/{job_id}/tasks", response_model=list[TaskWithOptions])
def get_job_tasks(job_id: int, db: Session = Depends(get_db)):
    return db.scalars(select(Task).where(Task.JobID == job_id).order_by(Task.Sequence)).all()


@job_extra.get("/{job_id}/dependencies", response_model=list[DependencyRead])
def get_job_dependencies(job_id: int, db: Session = Depends(get_db)):
    task_ids = select(Task.TaskID).where(Task.JobID == job_id)
    return db.scalars(
        select(TaskDependency)
        .where(TaskDependency.SuccessorTaskID.in_(task_ids))
        .order_by(TaskDependency.DependencyID)
    ).all()


routers = [
    job_extra,  # /jobs/{id}/tasks が隠れないよう先に登録する
    crud_router(Job, "/jobs", "Jobs", order_by="DueAt"),
    crud_router(Task, "/tasks", "Jobs", order_by="Sequence"),
    crud_router(TaskResourceOption, "/task-resource-options", "Jobs"),
    crud_router(TaskDependency, "/dependencies", "Jobs"),
]

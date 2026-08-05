from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.db.session import get_db
from app.models.background_job import (
    BackgroundJob,
    BackgroundJobStatus,
    BackgroundJobType,
)
from app.schemas.job import GmailSyncQueuedResponse
from app.worker.tasks.gmail import sync_gmail_task

router = APIRouter(
    prefix="/api/gmail",
    tags=["Gmail"],
)


@router.post(
    "/sync",
    response_model=GmailSyncQueuedResponse,
    status_code=202,
)
def queue_gmail_sync(
    request: Request,
    database: Annotated[Session, Depends(get_db)],
    max_threads: Annotated[int, Query(ge=1, le=100)] = 10,
) -> GmailSyncQueuedResponse:
    user_id = request.session.get("user_id")

    if not isinstance(user_id, int):
        raise AppError(
            status_code=401,
            error="authentication_required",
            message="Connect a Google account before synchronizing Gmail.",
        )

    existing_job = database.scalar(
        select(BackgroundJob).where(
            BackgroundJob.user_id == user_id,
            BackgroundJob.job_type == BackgroundJobType.GMAIL_SYNC.value,
            BackgroundJob.status.in_(
                [
                    BackgroundJobStatus.QUEUED.value,
                    BackgroundJobStatus.RUNNING.value,
                ]
            ),
        )
    )

    if existing_job is not None:
        raise AppError(
            status_code=409,
            error="gmail_sync_already_running",
            message="A Gmail synchronization job is already active.",
            details={
                "job_id": existing_job.id,
                "status": existing_job.status,
            },
        )

    job = BackgroundJob(
        user_id=user_id,
        job_type=BackgroundJobType.GMAIL_SYNC.value,
        status=BackgroundJobStatus.QUEUED.value,
        progress=0,
        parameters={
            "max_threads": max_threads,
        },
    )

    database.add(job)
    database.commit()
    database.refresh(job)

    task = sync_gmail_task.delay(
        job_id=job.id,
        user_id=user_id,
        max_threads=max_threads,
    )

    job.task_id = task.id
    database.commit()

    return GmailSyncQueuedResponse(
        job_id=job.id,
        task_id=task.id,
        status=job.status,
    )

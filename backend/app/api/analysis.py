from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import AppError
from app.db.session import get_db
from app.models.background_job import (
    BackgroundJob,
    BackgroundJobStatus,
    BackgroundJobType,
)
from app.models.email_thread import EmailThread
from app.models.thread_analysis import ThreadAnalysis
from app.schemas.analysis import (
    ThreadAnalysisQueuedResponse,
    ThreadAnalysisResponse,
)
from app.worker.tasks.analysis import analyze_thread_task

router = APIRouter(
    prefix="/api/threads",
    tags=["Thread analysis"],
)


def require_user_id(request: Request) -> int:
    user_id = request.session.get("user_id")

    if not isinstance(user_id, int):
        raise AppError(
            status_code=401,
            error="authentication_required",
            message="Authentication is required.",
        )

    return user_id


@router.post(
    "/{thread_id}/analyze",
    response_model=ThreadAnalysisQueuedResponse,
    status_code=202,
)
def queue_thread_analysis(
    thread_id: int,
    request: Request,
    database: Annotated[Session, Depends(get_db)],
    force: Annotated[bool, Query()] = False,
) -> ThreadAnalysisQueuedResponse:
    user_id = require_user_id(request)

    thread = database.scalar(
        select(EmailThread).where(
            EmailThread.id == thread_id,
            EmailThread.user_id == user_id,
        )
    )

    if thread is None:
        raise AppError(
            status_code=404,
            error="thread_not_found",
            message="The requested email thread was not found.",
            details={"thread_id": thread_id},
        )

    existing_job = database.scalar(
        select(BackgroundJob).where(
            BackgroundJob.user_id == user_id,
            BackgroundJob.job_type == BackgroundJobType.THREAD_ANALYSIS.value,
            BackgroundJob.status.in_(
                [
                    BackgroundJobStatus.QUEUED.value,
                    BackgroundJobStatus.RUNNING.value,
                ]
            ),
            BackgroundJob.parameters["thread_id"].as_integer() == thread_id,
        )
    )

    if existing_job is not None:
        raise AppError(
            status_code=409,
            error="thread_analysis_already_running",
            message="An analysis job is already active for this thread.",
            details={
                "job_id": existing_job.id,
                "thread_id": thread_id,
                "status": existing_job.status,
            },
        )

    job = BackgroundJob(
        user_id=user_id,
        job_type=BackgroundJobType.THREAD_ANALYSIS.value,
        status=BackgroundJobStatus.QUEUED.value,
        progress=0,
        parameters={
            "thread_id": thread_id,
            "force": force,
        },
    )

    database.add(job)
    database.commit()
    database.refresh(job)

    task = analyze_thread_task.delay(
        job_id=job.id,
        thread_id=thread_id,
        force=force,
    )

    job.task_id = task.id
    database.commit()

    return ThreadAnalysisQueuedResponse(
        job_id=job.id,
        task_id=task.id,
        status=job.status,
    )


@router.get(
    "/{thread_id}/analysis",
    response_model=ThreadAnalysisResponse,
)
def get_latest_thread_analysis(
    thread_id: int,
    request: Request,
    database: Annotated[Session, Depends(get_db)],
) -> ThreadAnalysisResponse:
    user_id = require_user_id(request)

    thread = database.scalar(
        select(EmailThread).where(
            EmailThread.id == thread_id,
            EmailThread.user_id == user_id,
        )
    )

    if thread is None:
        raise AppError(
            status_code=404,
            error="thread_not_found",
            message="The requested email thread was not found.",
            details={"thread_id": thread_id},
        )

    analysis = database.scalar(
        select(ThreadAnalysis)
        .options(
            selectinload(ThreadAnalysis.action_items),
            selectinload(ThreadAnalysis.suggested_replies),
        )
        .where(ThreadAnalysis.thread_id == thread_id)
        .order_by(ThreadAnalysis.created_at.desc())
    )

    if analysis is None:
        raise AppError(
            status_code=404,
            error="thread_analysis_not_found",
            message="This email thread has not been analyzed.",
            details={"thread_id": thread_id},
        )

    return ThreadAnalysisResponse.model_validate(analysis)

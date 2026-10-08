from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.auth import lock_job_owner, require_user_id
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
from app.services.entitlements import UsageLimitExceeded, consume_thread_analysis
from app.services.job_dispatch import dispatch_job
from app.services.thread_analysis import build_thread_fingerprint
from app.worker.tasks.analysis import analyze_thread_task

router = APIRouter(
    prefix="/api/threads",
    tags=["Thread analysis"],
)


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
    lock_job_owner(database, user_id)

    thread = database.scalar(
        select(EmailThread)
        .options(selectinload(EmailThread.messages))
        .where(
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

    if not thread.is_primary_inbox:
        raise AppError(
            status_code=422,
            error="thread_not_in_primary_inbox",
            message="Only synced Primary inbox conversations can be analyzed. Sync Gmail first.",
        )

    if not thread.messages:
        raise AppError(
            status_code=422,
            error="thread_has_no_messages",
            message="This conversation has no stored messages. Sync Gmail before analyzing it.",
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

    fingerprint = build_thread_fingerprint(thread)
    cached = (
        None
        if force
        else database.scalar(
            select(ThreadAnalysis.id)
            .where(
                ThreadAnalysis.thread_id == thread_id,
                ThreadAnalysis.source_fingerprint == fingerprint,
            )
            .limit(1)
        )
    )
    usage_event_id = None
    if cached is None:
        try:
            entitlement = consume_thread_analysis(database, user_id)
            usage_event_id = entitlement.usage_event_id
        except UsageLimitExceeded as exc:
            database.rollback()
            raise AppError(
                status_code=429,
                error="usage_limit_reached",
                message="You have used today's analyses. Your limit resets at midnight UTC.",
                details={"plan": exc.plan, "daily_limit": exc.limit, "used": exc.used},
            ) from exc

    job = BackgroundJob(
        user_id=user_id,
        job_type=BackgroundJobType.THREAD_ANALYSIS.value,
        status=BackgroundJobStatus.QUEUED.value,
        progress=0,
        parameters={
            "thread_id": thread_id,
            "force": force,
            "usage_event_id": usage_event_id,
        },
    )

    database.add(job)
    database.commit()
    database.refresh(job)

    task_id = dispatch_job(
        database,
        job,
        analyze_thread_task,
        thread_id=thread_id,
        force=force,
    )

    return ThreadAnalysisQueuedResponse(
        job_id=job.id,
        task_id=task_id,
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
        .order_by(ThreadAnalysis.created_at.desc(), ThreadAnalysis.id.desc())
    )

    if analysis is None:
        raise AppError(
            status_code=404,
            error="thread_analysis_not_found",
            message="This email thread has not been analyzed.",
            details={"thread_id": thread_id},
        )

    return ThreadAnalysisResponse.model_validate(analysis)

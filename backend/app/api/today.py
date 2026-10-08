from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import lock_job_owner, require_user_id
from app.core.exceptions import AppError
from app.db.session import get_db
from app.models.background_job import BackgroundJob
from app.schemas.job import BackgroundJobResponse
from app.services.job_dispatch import dispatch_job
from app.services.today import day_window
from app.worker.tasks.today import today_task

router = APIRouter(prefix="/api/today", tags=["Today's inbox"])


@router.post("", response_model=BackgroundJobResponse, status_code=202)
def load_today(
    request: Request,
    database: Annotated[Session, Depends(get_db)],
    time_zone: Annotated[str, Query(max_length=100)] = "UTC",
    analyze: bool = False,
):
    user_id = require_user_id(request)
    day, start, end = day_window(time_zone)
    lock_job_owner(database, user_id)
    active = database.scalar(
        select(BackgroundJob)
        .where(
            BackgroundJob.user_id == user_id,
            BackgroundJob.job_type == "today",
            BackgroundJob.status.in_(["queued", "running"]),
        )
        .order_by(BackgroundJob.id.desc())
    )
    if active is not None:
        created = (
            active.created_at.replace(tzinfo=UTC)
            if active.created_at.tzinfo is None
            else active.created_at
        )
        if created > datetime.now(UTC) - timedelta(minutes=65):
            same_day = (
                active.parameters.get("date") == day
                and active.parameters.get("time_zone") == time_zone
            )
            if same_day and (not analyze or active.parameters.get("analyze") is True):
                return BackgroundJobResponse.model_validate(active)
            raise AppError(
                status_code=409,
                error="today_busy",
                message="Wait for the current refresh to finish, then try again.",
            )
        active.status = "failed"
        active.error_message = "The previous job timed out. Preparing a new one."
        active.completed_at = datetime.now(UTC)
    job = BackgroundJob(
        user_id=user_id,
        job_type="today",
        status="queued",
        progress=0,
        parameters={
            "date": day,
            "time_zone": time_zone,
            "analyze": analyze,
            "start_at": start.isoformat(),
            "end_at": end.isoformat(),
        },
    )
    database.add(job)
    database.commit()
    database.refresh(job)
    dispatch_job(database, job, today_task)
    return BackgroundJobResponse.model_validate(job)

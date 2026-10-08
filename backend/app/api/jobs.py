from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import require_user_id
from app.core.exceptions import AppError
from app.db.session import get_db
from app.models.background_job import BackgroundJob
from app.schemas.job import BackgroundJobResponse

router = APIRouter(
    prefix="/api/jobs",
    tags=["Background jobs"],
)


@router.get("", response_model=list[BackgroundJobResponse])
def list_jobs(
    request: Request,
    database: Annotated[Session, Depends(get_db)],
) -> list[BackgroundJobResponse]:
    jobs = database.scalars(
        select(BackgroundJob)
        .where(BackgroundJob.user_id == require_user_id(request))
        .order_by(BackgroundJob.id.desc())
        .limit(50)
    ).all()
    return [BackgroundJobResponse.model_validate(job) for job in jobs]


@router.get(
    "/{job_id}",
    response_model=BackgroundJobResponse,
)
def get_job(
    job_id: int,
    request: Request,
    database: Annotated[Session, Depends(get_db)],
) -> BackgroundJobResponse:
    user_id = request.session.get("user_id")

    if not isinstance(user_id, int):
        raise AppError(
            status_code=401,
            error="authentication_required",
            message="Authentication is required.",
        )

    job = database.get(BackgroundJob, job_id)

    if job is None or job.user_id != user_id:
        raise AppError(
            status_code=404,
            error="job_not_found",
            message="The requested background job was not found.",
            details={"job_id": job_id},
        )

    return BackgroundJobResponse.model_validate(job)

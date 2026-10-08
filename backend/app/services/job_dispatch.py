from datetime import UTC, datetime
from uuid import uuid4

from celery import Task
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.models.background_job import BackgroundJob
from app.services.entitlements import refund_analysis_usage


def dispatch_job(database: Session, job: BackgroundJob, task: Task, **kwargs) -> str:
    """Persist a stable task ID before dispatch and make broker failure retryable."""
    task_id = str(uuid4())
    job.task_id = task_id
    database.commit()
    try:
        task.apply_async(kwargs={"job_id": job.id, **kwargs}, task_id=task_id, retry=False)
    except Exception as exc:
        refund_analysis_usage(database, job)
        job.status = "failed"
        job.error_message = "The job could not be queued. Please try again."
        job.completed_at = datetime.now(UTC)
        database.commit()
        raise AppError(
            status_code=503,
            error="queue_unavailable",
            message=job.error_message,
            details={"job_id": job.id},
        ) from exc
    return task_id

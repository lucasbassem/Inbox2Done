from datetime import UTC, datetime

from app.db.session import SessionLocal
from app.models.background_job import (
    BackgroundJob,
    BackgroundJobStatus,
)
from app.services.gmail_sync import sync_gmail_threads
from app.worker.celery_app import celery_app


@celery_app.task(
    bind=True,
    name="app.worker.tasks.gmail.sync_gmail",
)
def sync_gmail_task(
    self,
    *,
    job_id: int,
    user_id: int,
    max_threads: int,
) -> dict[str, int]:
    with SessionLocal() as database:
        job = database.get(BackgroundJob, job_id)

        if job is None:
            raise ValueError(f"Background job {job_id} was not found.")

        job.task_id = self.request.id
        job.status = BackgroundJobStatus.RUNNING.value
        job.progress = 10
        job.started_at = datetime.now(UTC)
        job.error_message = None
        database.commit()

        try:
            result = sync_gmail_threads(
                database=database,
                user_id=user_id,
                max_threads=max_threads,
            )

            job.status = BackgroundJobStatus.COMPLETED.value
            job.progress = 100
            job.result = result
            job.completed_at = datetime.now(UTC)
            database.commit()

            return result
        except Exception as exc:
            database.rollback()

            failed_job = database.get(BackgroundJob, job_id)

            if failed_job is not None:
                failed_job.status = BackgroundJobStatus.FAILED.value
                failed_job.error_message = str(exc)[:2000]
                failed_job.completed_at = datetime.now(UTC)
                database.commit()

            raise

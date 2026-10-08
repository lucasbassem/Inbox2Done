from datetime import UTC, datetime

from app.core.exceptions import AppError
from app.db.session import SessionLocal
from app.models.background_job import BackgroundJob
from app.services.today import prepare_today
from app.worker.celery_app import celery_app


@celery_app.task(
    bind=True, name="app.worker.tasks.today.prepare", soft_time_limit=3540, time_limit=3600
)
def today_task(self, *, job_id: int):
    with SessionLocal() as database:
        job = database.get(BackgroundJob, job_id)
        if job is None:
            raise ValueError("Today's inbox job was not found.")
        if job.status == "completed":
            return {"job_id": job_id, "status": "completed"}
        job.status = "running"
        job.task_id = self.request.id
        job.started_at = datetime.now(UTC)
        job.progress = 5
        database.commit()
        try:
            job.result = prepare_today(database, job)
            job.status = "completed"
            job.progress = 100
        except Exception as exc:
            database.rollback()
            job.status = "failed"
            job.error_message = (
                exc.message
                if isinstance(exc, AppError)
                else "Today's inbox was interrupted. Try again to resume."
            )
        job.completed_at = datetime.now(UTC)
        database.commit()
        return {"job_id": job_id, "status": job.status}

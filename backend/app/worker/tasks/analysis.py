from datetime import UTC, datetime

from sqlalchemy.orm import selectinload

from app.db.session import SessionLocal
from app.models.background_job import (
    BackgroundJob,
    BackgroundJobStatus,
)
from app.models.thread_analysis import ThreadAnalysis
from app.services.thread_analysis import analyze_thread
from app.worker.celery_app import celery_app


@celery_app.task(
    bind=True,
    name="app.worker.tasks.analysis.analyze_thread",
)
def analyze_thread_task(
    self,
    *,
    job_id: int,
    thread_id: int,
    force: bool = False,
) -> dict[str, int | str]:
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
            job.progress = 30
            database.commit()

            analysis = analyze_thread(
                database=database,
                thread_id=thread_id,
                force=force,
            )

            analysis = database.get(
                ThreadAnalysis,
                analysis.id,
                options=[
                    selectinload(ThreadAnalysis.action_items),
                    selectinload(ThreadAnalysis.suggested_replies),
                ],
            )

            if analysis is None:
                raise ValueError("Persisted thread analysis was not found.")

            result: dict[str, int | str] = {
                "thread_id": thread_id,
                "analysis_id": analysis.id,
                "summary": analysis.summary,
                "action_item_count": len(analysis.action_items),
                "suggested_reply_count": len(analysis.suggested_replies),
            }

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

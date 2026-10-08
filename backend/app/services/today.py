from copy import deepcopy
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from billiard.exceptions import SoftTimeLimitExceeded
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import AppError
from app.models.background_job import BackgroundJob
from app.models.email_message import EmailMessage
from app.models.email_thread import EmailThread
from app.models.thread_analysis import ThreadAnalysis
from app.schemas.analysis import ThreadAnalysisResponse
from app.services.gmail_sync import sync_gmail_threads
from app.services.thread_analysis import analyze_thread, build_thread_fingerprint


def day_window(time_zone: str, now: datetime | None = None):
    try:
        zone = ZoneInfo(time_zone)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise AppError(
            status_code=422, error="invalid_time_zone", message="Choose a valid local time zone."
        ) from exc
    day = (now or datetime.now(UTC)).astimezone(zone).date()
    start = datetime.combine(day, time.min, zone).astimezone(UTC)
    end = datetime.combine(day + timedelta(days=1), time.min, zone).astimezone(UTC)
    return day.isoformat(), start, end


def prepare_today(database: Session, job: BackgroundJob) -> dict:
    params = job.parameters
    sync = sync_gmail_threads(
        database=database,
        user_id=job.user_id,
        start_at=datetime.fromisoformat(params["start_at"]),
        end_at=datetime.fromisoformat(params["end_at"]),
    )
    result = {
        "date": params["date"],
        "time_zone": params["time_zone"],
        "message_count": len(sync["message_ids"]),
        "thread_count": len(sync["thread_ids"]),
        "analyzed_count": 0,
        "failed_count": 0,
        "items": [],
    }
    job.result = deepcopy(result)
    job.progress = 15
    database.commit()
    for index, thread_id in enumerate(sync["thread_ids"]):
        thread = database.scalar(
            select(EmailThread)
            .where(EmailThread.id == thread_id)
            .execution_options(populate_existing=True)
            .options(
                selectinload(
                    EmailThread.messages.and_(
                        EmailMessage.gmail_message_id.in_(sync["message_ids"])
                    )
                )
            )
        )
        item = {
            "thread_id": thread_id,
            "subject": thread.subject,
            "participants": thread.participants,
            "message_count": len(thread.messages),
            "snippet": thread.messages[-1].snippet if thread.messages else "",
            "analysis": None,
            "error": None,
        }
        try:
            if params.get("analyze") is True:
                analysis = analyze_thread(
                    database=database, thread_id=thread_id, message_ids=sync["message_ids"]
                )
            else:
                # Page loads only read cached results; only the Analyze button opts in.
                analysis = database.scalar(
                    select(ThreadAnalysis)
                    .where(
                        ThreadAnalysis.thread_id == thread_id,
                        ThreadAnalysis.source_fingerprint == build_thread_fingerprint(thread),
                    )
                    .options(
                        selectinload(ThreadAnalysis.action_items),
                        selectinload(ThreadAnalysis.suggested_replies),
                    )
                    .order_by(ThreadAnalysis.id.desc())
                    .limit(1)
                )
            if analysis is not None:
                item["analysis"] = ThreadAnalysisResponse.model_validate(analysis).model_dump(
                    mode="json"
                )
                result["analyzed_count"] += 1
        except SoftTimeLimitExceeded:
            raise
        except Exception as exc:
            database.rollback()
            item["error"] = (
                exc.message
                if isinstance(exc, AppError)
                else "This email could not be analyzed. Try again."
            )
            result["failed_count"] += 1
        result["items"].append(item)
        job.result = deepcopy(result)
        job.progress = 15 + int(80 * (index + 1) / max(1, result["thread_count"]))
        database.commit()
    return result

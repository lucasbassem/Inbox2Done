from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.db.session import get_db
from app.models.email_thread import EmailThread
from app.schemas.email_thread import EmailThreadPage, EmailThreadResponse

router = APIRouter(
    prefix="/api/threads",
    tags=["Threads"],
)


@router.get("", response_model=EmailThreadPage)
def list_threads(
    database: Annotated[Session, Depends(get_db)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    user_id: Annotated[int, Query(ge=1)] = 1,
) -> EmailThreadPage:
    total_statement = (
        select(func.count()).select_from(EmailThread).where(EmailThread.user_id == user_id)
    )

    total = database.scalar(total_statement) or 0
    offset = (page - 1) * page_size

    thread_statement = (
        select(EmailThread)
        .where(EmailThread.user_id == user_id)
        .order_by(
            EmailThread.latest_message_at.desc(),
            EmailThread.id.desc(),
        )
        .offset(offset)
        .limit(page_size)
    )

    threads = database.scalars(thread_statement).all()

    items = [EmailThreadResponse.model_validate(thread) for thread in threads]

    return EmailThreadPage.create(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get("/{thread_id}", response_model=EmailThreadResponse)
def get_thread(
    thread_id: int,
    database: Annotated[Session, Depends(get_db)],
) -> EmailThreadResponse:
    thread = database.get(EmailThread, thread_id)

    if thread is None:
        raise AppError(
            status_code=404,
            error="thread_not_found",
            message="The requested email thread was not found.",
            details={"thread_id": thread_id},
        )

    return EmailThreadResponse.model_validate(thread)

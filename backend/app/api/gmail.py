from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.db.session import get_db
from app.schemas.gmail import GmailSyncResponse
from app.services.gmail_sync import sync_gmail_threads

router = APIRouter(
    prefix="/api/gmail",
    tags=["Gmail"],
)


@router.post(
    "/sync",
    response_model=GmailSyncResponse,
)
def sync_gmail(
    request: Request,
    database: Annotated[Session, Depends(get_db)],
    max_threads: Annotated[int, Query(ge=1, le=100)] = 10,
) -> GmailSyncResponse:
    user_id = request.session.get("user_id")

    if not isinstance(user_id, int):
        raise AppError(
            status_code=401,
            error="authentication_required",
            message="Connect a Google account before synchronizing Gmail.",
        )

    result = sync_gmail_threads(
        database=database,
        user_id=user_id,
        max_threads=max_threads,
    )

    return GmailSyncResponse(
        user_id=user_id,
        **result,
    )

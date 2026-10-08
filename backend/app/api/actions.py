from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import require_user_id
from app.core.exceptions import AppError
from app.db.session import get_db
from app.models.action_item import ActionItem
from app.models.email_thread import EmailThread
from app.models.thread_analysis import ThreadAnalysis
from app.schemas.analysis import ActionItemResponse, ActionItemUpdate

router = APIRouter(prefix="/api/actions", tags=["Action items"])


@router.patch("/{action_id}", response_model=ActionItemResponse)
def update_action(
    action_id: int,
    update: ActionItemUpdate,
    request: Request,
    database: Annotated[Session, Depends(get_db)],
) -> ActionItemResponse:
    action = database.scalar(
        select(ActionItem)
        .join(ThreadAnalysis, ActionItem.analysis_id == ThreadAnalysis.id)
        .join(EmailThread, ThreadAnalysis.thread_id == EmailThread.id)
        .where(ActionItem.id == action_id, EmailThread.user_id == require_user_id(request))
    )
    if action is None:
        raise AppError(status_code=404, error="action_not_found", message="Action item not found.")
    changes = update.model_dump(exclude_unset=True)
    if any(key in changes and changes[key] is None for key in ("status", "priority")):
        raise AppError(
            status_code=422, error="invalid_action", message="Status and priority cannot be empty."
        )
    for key, value in changes.items():
        setattr(action, key, value)
    database.commit()
    database.refresh(action)
    return ActionItemResponse.model_validate(action)

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.models.user import User


def require_user_id(request: Request) -> int:
    user_id = request.session.get("user_id")
    if type(user_id) is not int or user_id < 1:
        raise AppError(
            status_code=401,
            error="authentication_required",
            message="Connect a Google account to continue.",
        )
    return user_id


def lock_job_owner(database: Session, user_id: int) -> None:
    """Serialize queue submissions for an account until its job record is committed."""
    if database.scalar(select(User).where(User.id == user_id).with_for_update()) is None:
        raise AppError(
            status_code=401,
            error="authentication_required",
            message="Connect a Google account to continue.",
        )

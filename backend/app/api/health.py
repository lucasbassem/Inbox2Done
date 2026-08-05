from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_db

router = APIRouter(tags=["Health"])


class LivenessResponse(BaseModel):
    status: Literal["ok"]
    service: str
    timestamp: datetime


class ReadinessResponse(BaseModel):
    status: Literal["ok"]
    service: str
    database: Literal["connected"]
    timestamp: datetime


@router.get(
    "/health/live",
    response_model=LivenessResponse,
    status_code=status.HTTP_200_OK,
)
def liveness_check() -> LivenessResponse:
    """Report whether the API process is alive.

    This endpoint deliberately avoids external dependencies. Container
    orchestrators may restart the process when this check fails.
    """
    return LivenessResponse(
        status="ok",
        service="inbox2done-api",
        timestamp=datetime.now(UTC),
    )


@router.get(
    "/health/ready",
    response_model=ReadinessResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "description": "The API is running but cannot reach PostgreSQL."
        }
    },
)
def readiness_check(
    database: Annotated[Session, Depends(get_db)],
) -> ReadinessResponse:
    """Report whether the API can serve requests that require PostgreSQL."""
    try:
        database.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "service_not_ready",
                "message": "Database connectivity check failed.",
            },
        ) from exc

    return ReadinessResponse(
        status="ok",
        service="inbox2done-api",
        database="connected",
        timestamp=datetime.now(UTC),
    )


@router.get(
    "/health",
    response_model=ReadinessResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
def health_check(
    database: Annotated[Session, Depends(get_db)],
) -> ReadinessResponse:
    """Backward-compatible alias for the readiness endpoint."""
    return readiness_check(database)

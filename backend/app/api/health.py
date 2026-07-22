from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_db

router = APIRouter(tags=["Health"])


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    service: str
    database: Literal["connected", "disconnected"]
    timestamp: datetime


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
)
def health_check(
    database: Annotated[Session, Depends(get_db)],
) -> HealthResponse:
    database_status: Literal["connected", "disconnected"] = "connected"
    application_status: Literal["ok", "degraded"] = "ok"

    try:
        database.execute(text("SELECT 1"))
    except SQLAlchemyError:
        database_status = "disconnected"
        application_status = "degraded"

    return HealthResponse(
        status=application_status,
        service="inbox2done-api",
        database=database_status,
        timestamp=datetime.now(UTC),
    )

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["Health"])


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    timestamp: datetime


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service="inbox2done-api",
        timestamp=datetime.now(UTC),
    )

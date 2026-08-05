from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class BackgroundJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: str | None
    user_id: int
    job_type: str
    status: str
    progress: int
    parameters: dict[str, Any]
    result: dict[str, Any] | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    updated_at: datetime


class GmailSyncQueuedResponse(BaseModel):
    job_id: int
    task_id: str
    status: str

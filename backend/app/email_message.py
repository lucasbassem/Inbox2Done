from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class EmailMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    thread_id: int
    gmail_message_id: str
    sender: str
    recipients: str
    cc: str
    subject: str
    snippet: str
    body_text: str
    body_html: str
    attachment_metadata: list[dict[str, Any]]
    sent_at: datetime | None
    created_at: datetime
    updated_at: datetime

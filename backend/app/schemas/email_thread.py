from datetime import datetime
from math import ceil

from pydantic import BaseModel, ConfigDict, Field


class EmailThreadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    gmail_thread_id: str
    subject: str
    snippet: str
    participants: str
    message_count: int
    latest_message_at: datetime
    created_at: datetime
    updated_at: datetime


class EmailThreadPage(BaseModel):
    items: list[EmailThreadResponse]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total: int = Field(ge=0)
    total_pages: int = Field(ge=0)
    has_next: bool
    has_previous: bool

    @classmethod
    def create(
        cls,
        *,
        items: list[EmailThreadResponse],
        page: int,
        page_size: int,
        total: int,
    ) -> "EmailThreadPage":
        total_pages = ceil(total / page_size) if total else 0

        return cls(
            items=items,
            page=page,
            page_size=page_size,
            total=total,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_previous=page > 1,
        )

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class GeneratedActionItem(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    description: str = ""
    owner: str | None = None
    due_at: datetime | None = None
    priority: Literal["low", "medium", "high", "urgent"] = "medium"


class GeneratedSuggestedReply(BaseModel):
    tone: Literal[
        "professional",
        "friendly",
        "concise",
        "formal",
    ] = "professional"

    subject: str | None = None
    body: str = Field(min_length=1)


class GeneratedThreadAnalysis(BaseModel):
    summary: str = Field(min_length=1)
    category: str = Field(min_length=1, max_length=100)
    priority: Literal["low", "medium", "high", "urgent"]
    sentiment: Literal[
        "positive",
        "neutral",
        "negative",
        "mixed",
    ]
    action_items: list[GeneratedActionItem] = Field(default_factory=list)
    suggested_replies: list[GeneratedSuggestedReply] = Field(default_factory=list)


class ActionItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    analysis_id: int
    title: str
    description: str
    owner: str | None
    due_at: datetime | None
    status: str
    priority: str
    created_at: datetime
    updated_at: datetime


class SuggestedReplyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    analysis_id: int
    tone: str
    subject: str | None
    body: str
    created_at: datetime


class ThreadAnalysisResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    thread_id: int
    model_name: str
    source_fingerprint: str
    summary: str
    category: str
    priority: str
    sentiment: str
    created_at: datetime
    updated_at: datetime
    action_items: list[ActionItemResponse]
    suggested_replies: list[SuggestedReplyResponse]

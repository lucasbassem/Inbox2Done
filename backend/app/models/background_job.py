from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class BackgroundJobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class BackgroundJobType(StrEnum):
    GMAIL_SYNC = "gmail_sync"


class BackgroundJob(Base):
    __tablename__ = "background_jobs"
    __table_args__ = (
        Index(
            "ix_background_jobs_user_type_status",
            "user_id",
            "job_type",
            "status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    task_id: Mapped[str | None] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
        ),
        index=True,
        nullable=False,
    )

    job_type: Mapped[str] = mapped_column(
        String(50),
        index=True,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(50),
        index=True,
        default=BackgroundJobStatus.QUEUED.value,
        nullable=False,
    )

    progress: Mapped[int] = mapped_column(
        default=0,
        nullable=False,
    )

    parameters: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
    )

    result: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.action_item import ActionItem
    from app.models.email_thread import EmailThread
    from app.models.suggested_reply import SuggestedReply


class ThreadAnalysis(Base):
    __tablename__ = "thread_analyses"
    __table_args__ = (
        Index(
            "ix_thread_analyses_thread_created",
            "thread_id",
            "created_at",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    thread_id: Mapped[int] = mapped_column(
        ForeignKey(
            "email_threads.id",
            ondelete="CASCADE",
        ),
        index=True,
        nullable=False,
    )

    model_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    source_fingerprint: Mapped[str] = mapped_column(
        String(64),
        index=True,
        nullable=False,
    )

    summary: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    category: Mapped[str] = mapped_column(
        String(100),
        default="general",
        nullable=False,
    )

    priority: Mapped[str] = mapped_column(
        String(20),
        default="medium",
        nullable=False,
    )

    sentiment: Mapped[str] = mapped_column(
        String(50),
        default="neutral",
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    thread: Mapped[EmailThread] = relationship(
        back_populates="analyses",
    )

    action_items: Mapped[list[ActionItem]] = relationship(
        back_populates="analysis",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    suggested_replies: Mapped[list[SuggestedReply]] = relationship(
        back_populates="analysis",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.email_message import EmailMessage
    from app.models.thread_analysis import ThreadAnalysis


class EmailThread(Base):
    __tablename__ = "email_threads"
    __table_args__ = (Index("ix_email_threads_user_latest", "user_id", "latest_message_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)

    gmail_thread_id: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
    )

    subject: Mapped[str] = mapped_column(
        String(998),
        default="",
        nullable=False,
    )

    snippet: Mapped[str] = mapped_column(
        Text,
        default="",
        nullable=False,
    )

    participants: Mapped[str] = mapped_column(
        Text,
        default="",
        nullable=False,
    )

    message_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    latest_message_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        index=True,
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
    messages: Mapped[list[EmailMessage]] = relationship(
        back_populates="thread",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="EmailMessage.sent_at",
    )
    analyses: Mapped[list[ThreadAnalysis]] = relationship(
        back_populates="thread",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ThreadAnalysis.created_at",
    )

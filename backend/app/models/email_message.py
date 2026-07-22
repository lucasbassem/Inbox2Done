from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.email_thread import EmailThread


class EmailMessage(Base):
    __tablename__ = "email_messages"

    id: Mapped[int] = mapped_column(primary_key=True)

    thread_id: Mapped[int] = mapped_column(
        ForeignKey(
            "email_threads.id",
            ondelete="CASCADE",
        ),
        index=True,
        nullable=False,
    )

    gmail_message_id: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
    )

    sender: Mapped[str] = mapped_column(
        String(998),
        default="",
        nullable=False,
    )

    recipients: Mapped[str] = mapped_column(
        Text,
        default="",
        nullable=False,
    )

    cc: Mapped[str] = mapped_column(
        Text,
        default="",
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

    body_text: Mapped[str] = mapped_column(
        Text,
        default="",
        nullable=False,
    )

    body_html: Mapped[str] = mapped_column(
        Text,
        default="",
        nullable=False,
    )

    attachment_metadata: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
    )

    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        index=True,
        nullable=True,
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
        back_populates="messages",
    )

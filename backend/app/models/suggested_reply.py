from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.thread_analysis import ThreadAnalysis


class SuggestedReply(Base):
    __tablename__ = "suggested_replies"

    id: Mapped[int] = mapped_column(primary_key=True)

    analysis_id: Mapped[int] = mapped_column(
        ForeignKey(
            "thread_analyses.id",
            ondelete="CASCADE",
        ),
        index=True,
        nullable=False,
    )

    tone: Mapped[str] = mapped_column(
        String(50),
        default="professional",
        nullable=False,
    )

    subject: Mapped[str | None] = mapped_column(
        String(998),
        nullable=True,
    )

    body: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    analysis: Mapped[ThreadAnalysis] = relationship(
        back_populates="suggested_replies",
    )

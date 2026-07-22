from datetime import UTC, datetime

import pytest
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.email_message import EmailMessage
from app.models.email_thread import EmailThread

test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

TestSessionLocal = sessionmaker(
    bind=test_engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)

Base.metadata.create_all(bind=test_engine)


def clear_data() -> None:
    with TestSessionLocal() as database:
        database.query(EmailMessage).delete()
        database.query(EmailThread).delete()
        database.commit()


def create_thread() -> int:
    with TestSessionLocal() as database:
        thread = EmailThread(
            user_id=1,
            gmail_thread_id="message-test-thread",
            subject="Message storage test",
            snippet="Testing message storage.",
            participants="sender@example.com",
            message_count=1,
            latest_message_at=datetime.now(UTC),
        )

        database.add(thread)
        database.commit()
        database.refresh(thread)

        return thread.id


def test_email_message_is_linked_to_thread() -> None:
    clear_data()
    thread_id = create_thread()

    with TestSessionLocal() as database:
        message = EmailMessage(
            thread_id=thread_id,
            gmail_message_id="gmail-message-001",
            sender="sender@example.com",
            recipients="recipient@example.com",
            subject="Test message",
            snippet="Test snippet",
            body_text="Test body",
            sent_at=datetime.now(UTC),
        )

        database.add(message)
        database.commit()
        database.refresh(message)

        assert message.id is not None
        assert message.thread_id == thread_id
        assert message.thread.id == thread_id
        assert message.thread.gmail_thread_id == "message-test-thread"


def test_duplicate_gmail_message_id_is_rejected() -> None:
    clear_data()
    thread_id = create_thread()

    with TestSessionLocal() as database:
        first_message = EmailMessage(
            thread_id=thread_id,
            gmail_message_id="duplicate-message-id",
            sender="sender@example.com",
            recipients="recipient@example.com",
            subject="First message",
            sent_at=datetime.now(UTC),
        )

        database.add(first_message)
        database.commit()

        duplicate_message = EmailMessage(
            thread_id=thread_id,
            gmail_message_id="duplicate-message-id",
            sender="sender@example.com",
            recipients="recipient@example.com",
            subject="Duplicate message",
            sent_at=datetime.now(UTC),
        )

        database.add(duplicate_message)

        with pytest.raises(IntegrityError):
            database.commit()

        database.rollback()

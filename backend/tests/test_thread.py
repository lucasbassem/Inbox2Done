from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.session import get_db
from app.main import app
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


def override_get_db():
    database = TestSessionLocal()

    try:
        yield database
    finally:
        database.close()


client = TestClient(app)


def clear_threads() -> None:
    with TestSessionLocal() as database:
        database.query(EmailMessage).delete()
        database.query(EmailThread).delete()
        database.commit()

@pytest.fixture(autouse=True)
def isolate_thread_database():
    previous_override = app.dependency_overrides.get(get_db)

    app.dependency_overrides[get_db] = override_get_db
    clear_threads()

    try:
        yield
    finally:
        clear_threads()

        if previous_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_override


def seed_threads(count: int = 5) -> None:
    now = datetime.now(UTC)

    with TestSessionLocal() as database:
        for index in range(count):
            database.add(
                EmailThread(
                    user_id=1,
                    gmail_thread_id=f"gmail-thread-{index}",
                    subject=f"Thread {index}",
                    snippet=f"Snippet {index}",
                    participants="sender@example.com",
                    message_count=index + 1,
                    latest_message_at=now - timedelta(minutes=index),
                )
            )

        database.commit()


def test_thread_pagination() -> None:
    clear_threads()
    seed_threads(5)

    response = client.get(
        "/api/threads",
        params={
            "page": 1,
            "page_size": 2,
            "user_id": 1,
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert len(body["items"]) == 2
    assert body["page"] == 1
    assert body["page_size"] == 2
    assert body["total"] == 5
    assert body["total_pages"] == 3
    assert body["has_next"] is True
    assert body["has_previous"] is False
    assert body["items"][0]["subject"] == "Thread 0"


def test_second_page_metadata() -> None:
    clear_threads()
    seed_threads(5)

    response = client.get(
        "/api/threads",
        params={
            "page": 2,
            "page_size": 2,
            "user_id": 1,
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert len(body["items"]) == 2
    assert body["page"] == 2
    assert body["total_pages"] == 3
    assert body["has_next"] is True
    assert body["has_previous"] is True


def test_invalid_page_size_is_rejected() -> None:
    response = client.get(
        "/api/threads",
        params={
            "page": 1,
            "page_size": 101,
            "user_id": 1,
        },
    )

    assert response.status_code == 422

    body = response.json()

    assert body["error"] == "validation_error"
    assert body["message"] == "The request contained invalid data."


def test_invalid_page_is_rejected() -> None:
    response = client.get(
        "/api/threads",
        params={
            "page": 0,
            "page_size": 20,
            "user_id": 1,
        },
    )

    assert response.status_code == 422


def test_get_thread_detail() -> None:
    clear_threads()
    seed_threads(1)

    with TestSessionLocal() as database:
        thread = database.query(EmailThread).first()

        assert thread is not None

        database.add(
            EmailMessage(
                thread_id=thread.id,
                gmail_message_id="detail-message-001",
                sender="sender@example.com",
                recipients="recipient@example.com",
                subject="Thread detail message",
                snippet="Stored message snippet",
                body_text="Stored message body",
                sent_at=datetime.now(UTC),
            )
        )

        database.commit()
        thread_id = thread.id

    response = client.get(f"/api/threads/{thread_id}")

    assert response.status_code == 200

    body = response.json()

    assert body["id"] == thread_id
    assert body["gmail_thread_id"] == "gmail-thread-0"
    assert body["subject"] == "Thread 0"
    assert body["message_count"] == 1

    assert len(body["messages"]) == 1
    assert body["messages"][0]["gmail_message_id"] == "detail-message-001"
    assert body["messages"][0]["body_text"] == "Stored message body"


def test_get_missing_thread_returns_structured_404() -> None:
    clear_threads()

    response = client.get("/api/threads/999999")

    assert response.status_code == 404

    body = response.json()

    assert body == {
        "error": "thread_not_found",
        "message": "The requested email thread was not found.",
        "details": {
            "thread_id": 999999,
        },
    }

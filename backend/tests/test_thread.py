from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.session import get_db
from app.main import app
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


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


def clear_threads() -> None:
    with TestSessionLocal() as database:
        database.query(EmailThread).delete()
        database.commit()


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

    list_response = client.get(
        "/api/threads",
        params={
            "page": 1,
            "page_size": 20,
            "user_id": 1,
        },
    )

    thread_id = list_response.json()["items"][0]["id"]

    response = client.get(f"/api/threads/{thread_id}")

    assert response.status_code == 200

    body = response.json()

    assert body["id"] == thread_id
    assert body["gmail_thread_id"] == "gmail-thread-0"
    assert body["subject"] == "Thread 0"
    assert body["message_count"] == 1


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

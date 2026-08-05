import base64
from datetime import UTC, datetime

import pytest
from sqlalchemy import StaticPool, create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.core.exceptions import AppError
from app.db.base import Base
from app.models.email_message import EmailMessage
from app.models.email_thread import EmailThread
from app.models.oauth_token import OAuthToken
from app.models.user import User
from app.services.gmail_sync import (
    decode_base64url,
    extract_message_content,
    get_headers,
    parse_internal_date,
    sync_gmail_threads,
)

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


def encode_base64url(value: str) -> str:
    encoded = base64.urlsafe_b64encode(value.encode("utf-8"))
    return encoded.decode("utf-8").rstrip("=")


def clear_data() -> None:
    with TestSessionLocal() as database:
        database.query(EmailMessage).delete()
        database.query(EmailThread).delete()
        database.query(OAuthToken).delete()
        database.query(User).delete()
        database.commit()


def create_connected_user() -> int:
    with TestSessionLocal() as database:
        user = User(
            email="gmail-sync@example.com",
            google_subject="google-sync-user",
            display_name="Gmail Sync User",
        )

        database.add(user)
        database.flush()

        database.add(
            OAuthToken(
                user_id=user.id,
                provider="google",
                access_token="test-access-token",
                refresh_token="test-refresh-token",
                token_type="Bearer",
                scopes=("openid email https://www.googleapis.com/auth/gmail.readonly"),
                expires_at=datetime(2030, 1, 1, tzinfo=UTC),
            )
        )

        database.commit()

        return user.id


class FakeRequest:
    def __init__(self, response: dict) -> None:
        self.response = response

    def execute(self) -> dict:
        return self.response


class FakeThreads:
    def list(
        self,
        *,
        userId: str,
        maxResults: int,
    ) -> FakeRequest:
        assert userId == "me"
        assert maxResults == 10

        return FakeRequest(
            {
                "threads": [
                    {
                        "id": "gmail-thread-001",
                    }
                ]
            }
        )

    def get(
        self,
        *,
        userId: str,
        id: str,
        format: str,
    ) -> FakeRequest:
        assert userId == "me"
        assert id == "gmail-thread-001"
        assert format == "full"

        return FakeRequest(
            {
                "id": "gmail-thread-001",
                "snippet": "Thread snippet",
                "messages": [
                    {
                        "id": "gmail-message-001",
                        "internalDate": "1800000000000",
                        "snippet": "Message snippet",
                        "payload": {
                            "mimeType": "multipart/alternative",
                            "headers": [
                                {
                                    "name": "From",
                                    "value": "Sender <sender@example.com>",
                                },
                                {
                                    "name": "To",
                                    "value": "recipient@example.com",
                                },
                                {
                                    "name": "Subject",
                                    "value": "Test Gmail Thread",
                                },
                            ],
                            "parts": [
                                {
                                    "mimeType": "text/plain",
                                    "filename": "",
                                    "body": {"data": encode_base64url("Plain text email body")},
                                },
                                {
                                    "mimeType": "text/html",
                                    "filename": "",
                                    "body": {"data": encode_base64url("<p>HTML email body</p>")},
                                },
                                {
                                    "mimeType": "application/pdf",
                                    "filename": "document.pdf",
                                    "body": {
                                        "attachmentId": "attachment-001",
                                        "size": 2048,
                                    },
                                },
                            ],
                        },
                    }
                ],
            }
        )


class FakeUsers:
    def threads(self) -> FakeThreads:
        return FakeThreads()


class FakeGmailService:
    def users(self) -> FakeUsers:
        return FakeUsers()


def test_decode_base64url() -> None:
    encoded = encode_base64url("Inbox2Done Gmail body")

    assert decode_base64url(encoded) == "Inbox2Done Gmail body"


def test_get_headers_normalizes_names() -> None:
    payload = {
        "headers": [
            {
                "name": "From",
                "value": "sender@example.com",
            },
            {
                "name": "SUBJECT",
                "value": "Important message",
            },
        ]
    }

    headers = get_headers(payload)

    assert headers["from"] == "sender@example.com"
    assert headers["subject"] == "Important message"


def test_extract_nested_message_content_and_attachment() -> None:
    payload = {
        "mimeType": "multipart/mixed",
        "parts": [
            {
                "mimeType": "multipart/alternative",
                "parts": [
                    {
                        "mimeType": "text/plain",
                        "body": {
                            "data": encode_base64url("Plain body"),
                        },
                    },
                    {
                        "mimeType": "text/html",
                        "body": {
                            "data": encode_base64url("<p>HTML body</p>"),
                        },
                    },
                ],
            },
            {
                "mimeType": "application/pdf",
                "filename": "report.pdf",
                "body": {
                    "attachmentId": "attachment-123",
                    "size": 4096,
                },
            },
        ],
    }

    body_text, body_html, attachments = extract_message_content(payload)

    assert body_text == "Plain body"
    assert body_html == "<p>HTML body</p>"
    assert attachments == [
        {
            "filename": "report.pdf",
            "mime_type": "application/pdf",
            "attachment_id": "attachment-123",
            "size": 4096,
        }
    ]


def test_parse_internal_date() -> None:
    result = parse_internal_date("1800000000000")

    assert result == datetime.fromtimestamp(
        1_800_000_000,
        tz=UTC,
    )


def test_sync_requires_connected_google_account() -> None:
    clear_data()

    with TestSessionLocal() as database:
        with pytest.raises(AppError) as error:
            sync_gmail_threads(
                database=database,
                user_id=999,
                max_threads=10,
            )

    assert error.value.status_code == 401
    assert error.value.error == "google_not_connected"


def test_sync_creates_then_updates_without_duplicates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_data()
    user_id = create_connected_user()

    monkeypatch.setattr(
        "app.services.gmail_sync.build_gmail_service",
        lambda database, oauth_token: FakeGmailService(),
    )

    with TestSessionLocal() as database:
        first_result = sync_gmail_threads(
            database=database,
            user_id=user_id,
            max_threads=10,
        )

        second_result = sync_gmail_threads(
            database=database,
            user_id=user_id,
            max_threads=10,
        )

        thread_count = database.scalar(select(func.count()).select_from(EmailThread))
        message_count = database.scalar(select(func.count()).select_from(EmailMessage))

        stored_thread = database.scalar(select(EmailThread))
        stored_message = database.scalar(select(EmailMessage))

    assert first_result == {
        "threads_fetched": 1,
        "threads_created": 1,
        "threads_updated": 0,
        "messages_created": 1,
        "messages_updated": 0,
    }

    assert second_result == {
        "threads_fetched": 1,
        "threads_created": 0,
        "threads_updated": 1,
        "messages_created": 0,
        "messages_updated": 1,
    }

    assert thread_count == 1
    assert message_count == 1

    assert stored_thread is not None
    assert stored_thread.subject == "Test Gmail Thread"
    assert stored_thread.message_count == 1

    assert stored_message is not None
    assert stored_message.gmail_message_id == "gmail-message-001"
    assert stored_message.body_text == "Plain text email body"
    assert stored_message.body_html == "<p>HTML email body</p>"
    assert stored_message.attachment_metadata[0]["filename"] == ("document.pdf")

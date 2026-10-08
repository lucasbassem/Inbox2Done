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
    create_google_credentials,
    decode_base64url,
    extract_message_content,
    get_headers,
    parse_internal_date,
    sync_gmail_threads,
)


def test_credentials_include_expiry():
    token = OAuthToken(
        access_token="access",
        refresh_token="refresh",
        scopes="",
        expires_at=datetime(2020, 1, 1, tzinfo=UTC),
    )
    credentials = create_google_credentials(token)
    assert credentials.expired


def test_mailboxes_with_matching_provider_ids_stay_separate(monkeypatch):
    clear_data()
    first_id = create_connected_user()
    monkeypatch.setattr(
        "app.services.gmail_sync.build_gmail_service",
        lambda database, oauth_token: FakeGmailService(),
    )
    with TestSessionLocal() as database:
        second = User(email="second@example.com", google_subject="second")
        database.add(second)
        database.flush()
        database.add(OAuthToken(user_id=second.id, provider="google", access_token="second-token"))
        database.commit()
        sync_gmail_threads(database=database, user_id=first_id)
        sync_gmail_threads(database=database, user_id=second.id)
        sync_gmail_threads(database=database, user_id=first_id)
        threads = database.scalars(select(EmailThread)).all()
        assert len(threads) == 2
        assert {thread.user_id for thread in threads} == {first_id, second.id}
        assert all(len(thread.messages) == 1 for thread in threads)


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
        q: str,
    ) -> FakeRequest:
        assert userId == "me"
        assert maxResults == 10
        assert q == "in:inbox category:primary"

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


def test_primary_sync_hides_legacy_mail_without_deleting_it(monkeypatch):
    clear_data()
    user_id = create_connected_user()
    monkeypatch.setattr(
        "app.services.gmail_sync.build_gmail_service", lambda *args: FakeGmailService()
    )
    with TestSessionLocal() as database:
        legacy = EmailThread(
            user_id=user_id,
            gmail_thread_id="demo-thread",
            is_primary_inbox=True,
            latest_message_at=datetime.now(UTC),
        )
        database.add(legacy)
        database.commit()
        sync_gmail_threads(database=database, user_id=user_id)
        database.refresh(legacy)
        assert not legacy.is_primary_inbox
        visible = database.scalars(
            select(EmailThread).where(EmailThread.is_primary_inbox.is_(True))
        ).all()
        assert len(visible) == 1
        assert visible[0].gmail_thread_id == "gmail-thread-001"
        assert len(visible[0].messages) == 1
        assert database.get(EmailThread, legacy.id) is not None


def test_today_sync_paginates_and_excludes_old_and_out_of_range_messages(monkeypatch):
    from copy import deepcopy
    from datetime import timedelta

    clear_data()
    user_id = create_connected_user()
    start = datetime.fromtimestamp(1800000000, tz=UTC)
    end = start + timedelta(days=1)
    calls = []

    class Messages:
        def list(self, **kwargs):
            calls.append(kwargs)
            assert "in:inbox category:primary" in kwargs["q"]
            assert f"before:{int(end.timestamp())}" in kwargs["q"]
            if kwargs["pageToken"] is None:
                return FakeRequest(
                    {
                        "messages": [{"id": "today", "threadId": "gmail-thread-001"}],
                        "nextPageToken": "next",
                    }
                )
            assert kwargs["pageToken"] == "next"
            return FakeRequest(
                {
                    "messages": [
                        {"id": "later", "threadId": "gmail-thread-001"},
                        {"id": "edge", "threadId": "gmail-thread-001"},
                    ]
                }
            )

    class Threads(FakeThreads):
        def get(self, **kwargs):
            data = super().get(**kwargs).execute()
            message = data["messages"][0]
            data["messages"] = []
            for id, when in [
                ("old", start - timedelta(seconds=1)),
                ("today", start),
                ("later", start + timedelta(hours=1)),
                ("edge", end),
            ]:
                copy = deepcopy(message)
                copy.update(id=id, internalDate=str(int(when.timestamp() * 1000)))
                data["messages"].append(copy)
            return FakeRequest(data)

    class Users:
        def messages(self):
            return Messages()

        def threads(self):
            return Threads()

    class Gmail:
        def users(self):
            return Users()

    monkeypatch.setattr("app.services.gmail_sync.build_gmail_service", lambda *args: Gmail())
    with TestSessionLocal() as db:
        result = sync_gmail_threads(database=db, user_id=user_id, start_at=start, end_at=end)
        assert result["message_ids"] == ["today", "later"]
        assert result["messages_created"] == 2
        assert len(result["thread_ids"]) == 1
    assert len(calls) == 2

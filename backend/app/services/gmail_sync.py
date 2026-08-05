from __future__ import annotations

import base64
from datetime import UTC, datetime
from email.utils import getaddresses
from typing import Any

from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import Resource, build
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AppError
from app.models.email_message import EmailMessage
from app.models.email_thread import EmailThread
from app.models.oauth_token import OAuthToken

GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"


def decode_base64url(data: str | None) -> str:
    if not data:
        return ""

    try:
        padding = "=" * (-len(data) % 4)
        decoded = base64.urlsafe_b64decode(data + padding)
        return decoded.decode("utf-8", errors="replace")
    except (ValueError, UnicodeDecodeError):
        return ""


def get_headers(payload: dict[str, Any]) -> dict[str, str]:
    headers = payload.get("headers", [])

    if not isinstance(headers, list):
        return {}

    result: dict[str, str] = {}

    for header in headers:
        if not isinstance(header, dict):
            continue

        name = header.get("name")
        value = header.get("value")

        if isinstance(name, str) and isinstance(value, str):
            result[name.lower()] = value

    return result


def normalize_addresses(value: str) -> str:
    addresses = getaddresses([value])

    normalized = [
        f"{name} <{address}>" if name else address for name, address in addresses if address
    ]

    return ", ".join(normalized)


def extract_message_content(
    payload: dict[str, Any],
) -> tuple[str, str, list[dict[str, Any]]]:
    text_parts: list[str] = []
    html_parts: list[str] = []
    attachments: list[dict[str, Any]] = []

    def visit(part: dict[str, Any]) -> None:
        mime_type = part.get("mimeType", "")
        filename = part.get("filename", "")
        body = part.get("body", {})

        if not isinstance(body, dict):
            body = {}

        attachment_id = body.get("attachmentId")

        if isinstance(filename, str) and filename:
            attachments.append(
                {
                    "filename": filename,
                    "mime_type": (mime_type if isinstance(mime_type, str) else ""),
                    "attachment_id": (attachment_id if isinstance(attachment_id, str) else None),
                    "size": (body.get("size") if isinstance(body.get("size"), int) else None),
                }
            )

        data = body.get("data")

        if isinstance(data, str):
            decoded = decode_base64url(data)

            if mime_type == "text/plain":
                text_parts.append(decoded)
            elif mime_type == "text/html":
                html_parts.append(decoded)

        parts = part.get("parts", [])

        if isinstance(parts, list):
            for child in parts:
                if isinstance(child, dict):
                    visit(child)

    visit(payload)

    return (
        "\n".join(part for part in text_parts if part).strip(),
        "\n".join(part for part in html_parts if part).strip(),
        attachments,
    )


def parse_internal_date(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None

    try:
        milliseconds = int(value)
        return datetime.fromtimestamp(milliseconds / 1000, tz=UTC)
    except (TypeError, ValueError, OSError):
        return None


def create_google_credentials(
    oauth_token: OAuthToken,
) -> Credentials:
    scopes = oauth_token.scopes.split() if oauth_token.scopes else None

    credentials = Credentials(
        token=oauth_token.access_token,
        refresh_token=oauth_token.refresh_token,
        token_uri=GOOGLE_TOKEN_URI,
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        scopes=scopes,
    )

    return credentials


def build_gmail_service(
    database: Session,
    oauth_token: OAuthToken,
) -> Resource:
    credentials = create_google_credentials(oauth_token)

    if not credentials.valid:
        if not credentials.refresh_token:
            raise AppError(
                status_code=401,
                error="google_refresh_token_missing",
                message=("Google authorization must be completed again to obtain a refresh token."),
            )

        try:
            credentials.refresh(GoogleAuthRequest())
        except Exception as exc:
            raise AppError(
                status_code=401,
                error="google_token_refresh_failed",
                message="The Google access token could not be refreshed.",
            ) from exc

        oauth_token.access_token = credentials.token

        if credentials.expiry is not None:
            oauth_token.expires_at = credentials.expiry

        database.commit()

    return build(
        "gmail",
        "v1",
        credentials=credentials,
        cache_discovery=False,
    )


def sync_gmail_threads(
    *,
    database: Session,
    user_id: int,
    max_threads: int = 10,
) -> dict[str, int]:
    oauth_token = database.scalar(
        select(OAuthToken).where(
            OAuthToken.user_id == user_id,
            OAuthToken.provider == "google",
        )
    )

    if oauth_token is None:
        raise AppError(
            status_code=401,
            error="google_not_connected",
            message="Connect a Google account before synchronizing Gmail.",
        )

    gmail = build_gmail_service(database, oauth_token)

    response = (
        gmail.users()
        .threads()
        .list(
            userId="me",
            maxResults=max_threads,
        )
        .execute()
    )

    thread_summaries = response.get("threads", [])

    if not isinstance(thread_summaries, list):
        thread_summaries = []

    threads_created = 0
    threads_updated = 0
    messages_created = 0
    messages_updated = 0

    for summary in thread_summaries:
        if not isinstance(summary, dict):
            continue

        gmail_thread_id = summary.get("id")

        if not isinstance(gmail_thread_id, str):
            continue

        gmail_thread = (
            gmail.users()
            .threads()
            .get(
                userId="me",
                id=gmail_thread_id,
                format="full",
            )
            .execute()
        )

        gmail_messages = gmail_thread.get("messages", [])

        if not isinstance(gmail_messages, list) or not gmail_messages:
            continue

        parsed_messages: list[dict[str, Any]] = []

        for gmail_message in gmail_messages:
            if not isinstance(gmail_message, dict):
                continue

            gmail_message_id = gmail_message.get("id")
            payload = gmail_message.get("payload", {})

            if not isinstance(gmail_message_id, str):
                continue

            if not isinstance(payload, dict):
                payload = {}

            headers = get_headers(payload)
            body_text, body_html, attachments = extract_message_content(payload)
            sent_at = parse_internal_date(gmail_message.get("internalDate"))

            parsed_messages.append(
                {
                    "gmail_message_id": gmail_message_id,
                    "sender": normalize_addresses(headers.get("from", "")),
                    "recipients": normalize_addresses(headers.get("to", "")),
                    "cc": normalize_addresses(headers.get("cc", "")),
                    "subject": headers.get("subject", ""),
                    "snippet": str(gmail_message.get("snippet", "")),
                    "body_text": body_text,
                    "body_html": body_html,
                    "attachment_metadata": attachments,
                    "sent_at": sent_at,
                }
            )

        if not parsed_messages:
            continue

        parsed_messages.sort(key=lambda item: item["sent_at"] or datetime.min.replace(tzinfo=UTC))

        latest_message = parsed_messages[-1]

        participants = sorted(
            {
                address
                for message in parsed_messages
                for address in (
                    message["sender"],
                    message["recipients"],
                    message["cc"],
                )
                if address
            }
        )

        email_thread = database.scalar(
            select(EmailThread).where(
                EmailThread.user_id == user_id,
                EmailThread.gmail_thread_id == gmail_thread_id,
            )
        )

        if email_thread is None:
            email_thread = EmailThread(
                user_id=user_id,
                gmail_thread_id=gmail_thread_id,
                subject=latest_message["subject"],
                snippet=str(gmail_thread.get("snippet", "")),
                participants=", ".join(participants),
                message_count=len(parsed_messages),
                latest_message_at=latest_message["sent_at"],
            )
            database.add(email_thread)
            database.flush()
            threads_created += 1
        else:
            email_thread.subject = latest_message["subject"]
            email_thread.snippet = str(gmail_thread.get("snippet", ""))
            email_thread.participants = ", ".join(participants)
            email_thread.message_count = len(parsed_messages)
            email_thread.latest_message_at = latest_message["sent_at"]
            threads_updated += 1

        for parsed_message in parsed_messages:
            email_message = database.scalar(
                select(EmailMessage).where(
                    EmailMessage.gmail_message_id == parsed_message["gmail_message_id"]
                )
            )

            if email_message is None:
                email_message = EmailMessage(
                    thread_id=email_thread.id,
                    **parsed_message,
                )
                database.add(email_message)
                messages_created += 1
            else:
                email_message.thread_id = email_thread.id
                email_message.sender = parsed_message["sender"]
                email_message.recipients = parsed_message["recipients"]
                email_message.cc = parsed_message["cc"]
                email_message.subject = parsed_message["subject"]
                email_message.snippet = parsed_message["snippet"]
                email_message.body_text = parsed_message["body_text"]
                email_message.body_html = parsed_message["body_html"]
                email_message.attachment_metadata = parsed_message["attachment_metadata"]
                email_message.sent_at = parsed_message["sent_at"]
                messages_updated += 1

    database.commit()

    return {
        "threads_fetched": len(thread_summaries),
        "threads_created": threads_created,
        "threads_updated": threads_updated,
        "messages_created": messages_created,
        "messages_updated": messages_updated,
    }

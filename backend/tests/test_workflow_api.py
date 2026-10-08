from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine, select
from sqlalchemy.orm import Session

from app.api import auth
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.action_item import ActionItem
from app.models.background_job import BackgroundJob
from app.models.email_message import EmailMessage
from app.models.email_thread import EmailThread
from app.models.thread_analysis import ThreadAnalysis
from app.models.user import User
from app.worker.tasks.analysis import analyze_thread_task
from app.worker.tasks.gmail import sync_gmail_task
from tests.session_helpers import session_cookie


@pytest.fixture
def workflow():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as database:
        user = User(id=1, email="owner@example.com", google_subject="owner")
        other = User(id=2, email="other@example.com", google_subject="other")
        thread = EmailThread(
            user_id=1,
            is_primary_inbox=True,
            gmail_thread_id="owner-thread",
            subject="Project review",
            latest_message_at=datetime.now(UTC),
        )
        private = EmailThread(
            user_id=2,
            gmail_thread_id="private-thread",
            subject="Private",
            latest_message_at=datetime.now(UTC),
        )
        database.add_all([user, other, thread, private])
        database.flush()
        database.add(
            EmailMessage(
                thread_id=thread.id,
                gmail_message_id="owner-message",
                body_text="Review the project",
            )
        )
        database.flush()
        analysis = ThreadAnalysis(
            thread_id=thread.id,
            model_name="test",
            source_fingerprint="abc",
            summary="Review the project",
            category="work",
            priority="high",
            sentiment="neutral",
        )
        analysis.action_items.append(ActionItem(title="Send review", description="Read the draft"))
        database.add(analysis)
        database.commit()
        app.dependency_overrides[get_db] = lambda: database
        with TestClient(app) as client:
            client.cookies.set("session", session_cookie(1), domain="testserver.local", path="/")
            yield SimpleNamespace(
                client=client,
                db=database,
                thread=thread,
                private=private,
                analysis=analysis,
                action=analysis.action_items[0],
            )
        app.dependency_overrides.pop(get_db, None)
    engine.dispose()


def test_thread_reads_require_authentication(workflow):
    workflow.client.cookies.clear()
    for path in ("/api/threads", f"/api/threads/{workflow.thread.id}", "/api/jobs"):
        assert workflow.client.get(path).status_code == 401


def test_user_cannot_read_another_users_threads(workflow):
    result = workflow.client.get("/api/threads?user_id=2").json()
    assert [item["subject"] for item in result["items"]] == ["Project review"]
    assert workflow.client.get(f"/api/threads/{workflow.private.id}").status_code == 404
    assert workflow.client.get(f"/api/threads/{workflow.private.id}/analysis").status_code == 404
    assert workflow.client.post(f"/api/threads/{workflow.private.id}/analyze").status_code == 404


def test_complete_and_reopen_action_persists(workflow):
    path = f"/api/actions/{workflow.action.id}"
    assert workflow.client.patch(path, json={"status": "completed"}).json()["status"] == "completed"
    result = workflow.client.get(f"/api/threads/{workflow.thread.id}/analysis").json()
    assert result["action_items"][0]["status"] == "completed"
    assert workflow.client.patch(path, json={"status": "open"}).json()["status"] == "open"
    assert workflow.client.patch(path, json={"status": "invented"}).status_code == 422
    assert workflow.client.patch(path, json={"status": None}).status_code == 422


def test_action_updates_require_owner(workflow):
    workflow.client.cookies.set("session", session_cookie(2), domain="testserver.local", path="/")
    assert (
        workflow.client.patch(
            f"/api/actions/{workflow.action.id}", json={"status": "completed"}
        ).status_code
        == 404
    )
    workflow.client.cookies.clear()
    assert (
        workflow.client.patch(
            f"/api/actions/{workflow.action.id}", json={"status": "completed"}
        ).status_code
        == 401
    )


@pytest.mark.parametrize("kind", ["sync", "analysis"])
def test_job_dispatch_duplicate_guard_and_owner_polling(workflow, monkeypatch, kind):
    task = sync_gmail_task if kind == "sync" else analyze_thread_task
    dispatch = Mock()
    monkeypatch.setattr(task, "apply_async", dispatch)
    path = "/api/gmail/sync" if kind == "sync" else f"/api/threads/{workflow.thread.id}/analyze"
    response = workflow.client.post(path)
    assert response.status_code == 202
    body = response.json()
    assert dispatch.call_args.kwargs["task_id"] == body["task_id"]
    assert workflow.client.post(path).status_code == 409
    assert workflow.client.get(f"/api/jobs/{body['job_id']}").status_code == 200
    assert len(workflow.client.get("/api/jobs").json()) == 1
    workflow.client.cookies.set("session", session_cookie(2), domain="testserver.local", path="/")
    assert workflow.client.get("/api/jobs").json() == []
    assert workflow.client.get(f"/api/jobs/{body['job_id']}").status_code == 404


@pytest.mark.parametrize("kind", ["sync", "analysis"])
def test_queue_outage_marks_failed_and_allows_retry(workflow, monkeypatch, kind):
    task = sync_gmail_task if kind == "sync" else analyze_thread_task
    dispatch = Mock(side_effect=ConnectionError("private broker details"))
    monkeypatch.setattr(task, "apply_async", dispatch)
    path = "/api/gmail/sync" if kind == "sync" else f"/api/threads/{workflow.thread.id}/analyze"
    response = workflow.client.post(path)
    assert response.status_code == 503
    assert "private broker" not in response.text
    job = workflow.db.scalar(select(BackgroundJob))
    assert job.status == "failed"
    assert job.completed_at is not None
    dispatch.side_effect = None
    assert workflow.client.post(path).status_code == 202


def test_logout_clears_session(workflow):
    assert workflow.client.post("/api/auth/google/logout").status_code == 200
    assert workflow.client.get("/api/threads").status_code == 401


def test_oauth_callback_redirects_to_frontend(workflow, monkeypatch):
    async def authorize(_request):
        return {
            "access_token": "test-token",
            "userinfo": {"email": "owner@example.com", "sub": "owner"},
        }

    monkeypatch.setattr(
        auth.oauth, "create_client", lambda _: SimpleNamespace(authorize_access_token=authorize)
    )
    response = workflow.client.get("/api/auth/google/callback", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == auth.settings.frontend_origin
    assert workflow.client.get("/api/auth/google/status").json()["connected"] is True


def test_cross_origin_writes_are_rejected(workflow):
    response = workflow.client.patch(
        f"/api/actions/{workflow.action.id}",
        json={"status": "completed"},
        headers={"Origin": "https://untrusted.example"},
    )
    assert response.status_code == 403
    assert (
        workflow.client.post(
            "/api/auth/google/logout", headers={"Sec-Fetch-Site": "cross-site"}
        ).status_code
        == 403
    )
    assert (
        workflow.client.post(
            "/api/auth/google/logout", headers={"Origin": auth.settings.frontend_origin}
        ).status_code
        == 200
    )


@pytest.mark.parametrize("empty", [False, True])
def test_invalid_analysis_does_not_reserve_quota_or_dispatch(workflow, monkeypatch, empty):
    from app.models.usage_event import UsageEvent

    if empty:
        workflow.db.query(EmailMessage).delete()
        workflow.db.expire(workflow.thread, ["messages"])
    else:
        workflow.thread.is_primary_inbox = False
    workflow.db.commit()
    dispatch = Mock()
    monkeypatch.setattr(analyze_thread_task, "apply_async", dispatch)
    response = workflow.client.post(f"/api/threads/{workflow.thread.id}/analyze")
    assert response.status_code == 422
    assert response.json()["error"] == (
        "thread_has_no_messages" if empty else "thread_not_in_primary_inbox"
    )
    assert workflow.db.scalar(select(UsageEvent)) is None
    assert workflow.db.scalar(select(BackgroundJob)) is None
    dispatch.assert_not_called()


def test_only_primary_threads_are_visible(workflow):
    workflow.thread.is_primary_inbox = False
    workflow.db.commit()
    assert workflow.client.get("/api/threads").json()["total"] == 0
    assert workflow.client.get(f"/api/threads/{workflow.thread.id}").status_code == 404

from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import pytest
from sqlalchemy import select

from app.models.background_job import BackgroundJob
from app.models.email_message import EmailMessage
from app.services.thread_analysis import analyze_thread
from app.services.today import day_window, prepare_today
from app.worker.tasks.today import today_task
from tests.test_thread_analysis_service import FakeOpenAI, generated_analysis
from tests.test_workflow_api import workflow as workflow


@pytest.mark.parametrize(
    "instant,day,hours",
    [
        (datetime(2026, 10, 8, 2, tzinfo=UTC), "2026-10-07", 24),
        (datetime(2026, 3, 8, 15, tzinfo=UTC), "2026-03-08", 23),
        (datetime(2026, 11, 1, 15, tzinfo=UTC), "2026-11-01", 25),
    ],
)
def test_local_day_and_dst(instant, day, hours):
    actual, start, end = day_window("America/New_York", instant)
    assert actual == day
    assert end - start == timedelta(hours=hours)


def test_today_requires_auth_and_valid_zone(workflow):
    assert workflow.client.post("/api/today?time_zone=invalid").status_code == 422
    workflow.client.cookies.clear()
    assert workflow.client.post("/api/today").status_code == 401


def test_load_never_opts_in_and_duplicate_load_reuses_job(workflow, monkeypatch):
    dispatch = Mock()
    monkeypatch.setattr(today_task, "apply_async", dispatch)
    first = workflow.client.post("/api/today?time_zone=America/New_York")
    assert first.status_code == 202
    assert first.json()["parameters"]["analyze"] is False
    second = workflow.client.post("/api/today?time_zone=America/New_York")
    assert second.json()["id"] == first.json()["id"]
    assert dispatch.call_count == 1
    assert (
        workflow.client.post("/api/today?time_zone=America/New_York&analyze=true").status_code
        == 409
    )
    job = workflow.db.get(BackgroundJob, first.json()["id"])
    job.status = "completed"
    workflow.db.commit()
    requested = workflow.client.post("/api/today?time_zone=America/New_York&analyze=true")
    assert requested.json()["parameters"]["analyze"] is True


def test_load_is_read_only_for_ai_and_click_uses_only_selected_messages(workflow, monkeypatch):
    db = workflow.db
    db.add(
        EmailMessage(
            thread_id=workflow.thread.id, gmail_message_id="yesterday", body_text="PRIVATE OLD BODY"
        )
    )
    db.commit()
    monkeypatch.setattr(
        "app.services.today.sync_gmail_threads",
        lambda **kwargs: {"thread_ids": [workflow.thread.id], "message_ids": ["owner-message"]},
    )
    day, start, end = day_window("UTC")
    job = BackgroundJob(
        user_id=1,
        job_type="today",
        parameters={
            "date": day,
            "time_zone": "UTC",
            "start_at": start.isoformat(),
            "end_at": end.isoformat(),
            "analyze": False,
        },
    )
    db.add(job)
    db.commit()
    spy = Mock(side_effect=AssertionError("Page load must not call AI"))
    monkeypatch.setattr("app.services.today.analyze_thread", spy)
    result = prepare_today(db, job)
    db.expire(job, ["result"])
    assert len(job.result["items"]) == 1
    assert result["message_count"] == 1
    assert result["analyzed_count"] == 0
    spy.assert_not_called()
    fake = FakeOpenAI(generated_analysis())
    captured = []
    original_parse = fake.responses.parse

    def parse(**kwargs):
        captured.append(kwargs["input"][1]["content"])
        return original_parse(**kwargs)

    fake.responses.parse = parse
    monkeypatch.setattr(
        "app.services.today.analyze_thread", lambda **kwargs: analyze_thread(**kwargs, client=fake)
    )
    job.parameters = {**job.parameters, "analyze": True}
    db.commit()
    result = prepare_today(db, job)
    assert result["analyzed_count"] == 1
    assert "PRIVATE OLD BODY" not in captured[0]
    assert "Review the project" in captured[0]
    prepare_today(db, job)
    assert fake.responses.call_count == 1
    job.parameters = {**job.parameters, "analyze": False}
    db.commit()
    assert prepare_today(db, job)["analyzed_count"] == 1
    assert fake.responses.call_count == 1
    assert len(db.scalars(select(EmailMessage)).all()) == 2

from collections.abc import Generator
from unittest.mock import MagicMock

from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.main import app


def override_healthy_db() -> Generator[Session, None, None]:
    database = MagicMock(spec=Session)
    yield database


client = TestClient(app)

def restore_db_override(previous_override) -> None:
    if previous_override is None:
        app.dependency_overrides.pop(get_db, None)
    else:
        app.dependency_overrides[get_db] = previous_override


def test_liveness_does_not_require_database() -> None:
    response = client.get("/health/live")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "inbox2done-api"
    assert "timestamp" in body


def test_readiness_reports_database_connection() -> None:
    previous_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_healthy_db

    try:
        response = client.get("/health/ready")
    finally:
        restore_db_override(previous_override)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "inbox2done-api"
    assert body["database"] == "connected"
    assert "timestamp" in body


def test_readiness_returns_503_when_database_is_unavailable() -> None:
    database = MagicMock(spec=Session)
    database.execute.side_effect = OperationalError(
        statement="SELECT 1",
        params={},
        orig=RuntimeError("database unavailable"),
    )

    def override_unhealthy_db() -> Generator[Session, None, None]:
        yield database

    previous_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_unhealthy_db

    try:
        response = client.get("/health/ready")
    finally:
        restore_db_override(previous_override)

    assert response.status_code == 503
    body = response.json()
    assert body["detail"]["code"] == "service_not_ready"


def test_legacy_health_endpoint_remains_available() -> None:
    previous_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_healthy_db

    try:
        response = client.get("/health")
    finally:
        restore_db_override(previous_override)

    assert response.status_code == 200
    assert response.json()["database"] == "connected"

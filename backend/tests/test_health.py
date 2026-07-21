from unittest.mock import MagicMock

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.main import app


def override_get_db() -> Session:
    database = MagicMock(spec=Session)
    yield database


app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)


def test_health_endpoint() -> None:
    response = client.get("/health")

    assert response.status_code == 200

    body = response.json()

    assert body["status"] == "ok"
    assert body["service"] == "inbox2done-api"
    assert body["database"] == "connected"
    assert "timestamp" in body
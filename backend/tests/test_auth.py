from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.api.auth import calculate_expiry
from app.core.config import settings
from app.main import app

client = TestClient(app)


def test_google_status_returns_disconnected_without_session() -> None:
    response = client.get("/api/auth/google/status")

    assert response.status_code == 200
    assert response.json() == {
        "connected": False,
        "user_id": None,
        "email": None,
        "display_name": None,
        "expires_at": None,
    }


def test_google_login_returns_503_without_credentials(
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "google_client_id", "")
    monkeypatch.setattr(settings, "google_client_secret", "")

    response = client.get(
        "/api/auth/google/login",
        follow_redirects=False,
    )

    assert response.status_code == 503
    assert response.json() == {
        "error": "google_oauth_not_configured",
        "message": "Google OAuth credentials are not configured.",
        "details": None,
    }


def test_calculate_expiry_uses_absolute_timestamp() -> None:
    timestamp = 1_800_000_000

    result = calculate_expiry(
        {
            "expires_at": timestamp,
        }
    )

    assert result == datetime.fromtimestamp(timestamp, tz=UTC)


def test_calculate_expiry_returns_none_without_expiry() -> None:
    result = calculate_expiry({})

    assert result is None

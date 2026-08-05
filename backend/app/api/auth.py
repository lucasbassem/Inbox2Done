from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from authlib.integrations.base_client.errors import OAuthError
from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse

from app.core.config import settings
from app.core.exceptions import AppError
from app.db.session import get_db
from app.models.oauth_token import OAuthToken
from app.models.user import User
from app.schemas.auth import (
    GoogleConnectionStatus,
    GoogleOAuthCallbackResponse,
)
from app.services.google_oauth import oauth

router = APIRouter(
    prefix="/api/auth/google",
    tags=["Google authentication"],
)


def calculate_expiry(token: dict[str, Any]) -> datetime | None:
    expires_at = token.get("expires_at")

    if isinstance(expires_at, int | float):
        return datetime.fromtimestamp(expires_at, tz=UTC)

    expires_in = token.get("expires_in")

    if isinstance(expires_in, int | float):
        return datetime.now(UTC) + timedelta(seconds=expires_in)

    return None


@router.get("/login")
async def google_login(request: Request) -> RedirectResponse:
    if not settings.google_client_id or not settings.google_client_secret:
        raise AppError(
            status_code=503,
            error="google_oauth_not_configured",
            message="Google OAuth credentials are not configured.",
        )

    google = oauth.create_client("google")

    if google is None:
        raise AppError(
            status_code=500,
            error="google_oauth_client_unavailable",
            message="The Google OAuth client could not be initialized.",
        )

    return await google.authorize_redirect(
        request,
        settings.google_redirect_uri,
        access_type="offline",
        prompt="consent",
        include_granted_scopes="true",
    )


@router.get(
    "/callback",
    response_model=GoogleOAuthCallbackResponse,
)
async def google_callback(
    request: Request,
    database: Annotated[Session, Depends(get_db)],
) -> GoogleOAuthCallbackResponse:
    google = oauth.create_client("google")

    if google is None:
        raise AppError(
            status_code=500,
            error="google_oauth_client_unavailable",
            message="The Google OAuth client could not be initialized.",
        )

    try:
        token = await google.authorize_access_token(request)
    except OAuthError as exc:
        raise AppError(
            status_code=400,
            error="google_oauth_failed",
            message="Google authorization failed.",
            details={"reason": exc.error},
        ) from exc

    user_info = token.get("userinfo")

    if not isinstance(user_info, dict):
        raise AppError(
            status_code=502,
            error="google_userinfo_missing",
            message="Google did not return the expected user information.",
        )

    email = user_info.get("email")
    google_subject = user_info.get("sub")

    if not isinstance(email, str) or not isinstance(
        google_subject,
        str,
    ):
        raise AppError(
            status_code=502,
            error="google_identity_invalid",
            message="Google returned incomplete identity information.",
        )

    user = database.scalar(select(User).where(User.google_subject == google_subject))

    if user is None:
        user = database.scalar(select(User).where(User.email == email))

    if user is None:
        user = User(
            email=email,
            google_subject=google_subject,
        )
        database.add(user)
        database.flush()
    else:
        user.google_subject = google_subject

    display_name = user_info.get("name")
    picture_url = user_info.get("picture")

    user.display_name = display_name if isinstance(display_name, str) else None
    user.picture_url = picture_url if isinstance(picture_url, str) else None

    oauth_token = database.scalar(
        select(OAuthToken).where(
            OAuthToken.user_id == user.id,
            OAuthToken.provider == "google",
        )
    )

    refresh_token = token.get("refresh_token")

    if oauth_token is None:
        oauth_token = OAuthToken(
            user_id=user.id,
            provider="google",
            access_token=str(token["access_token"]),
        )
        database.add(oauth_token)

    oauth_token.access_token = str(token["access_token"])
    oauth_token.token_type = str(token.get("token_type", "Bearer"))
    oauth_token.expires_at = calculate_expiry(token)

    if isinstance(refresh_token, str):
        oauth_token.refresh_token = refresh_token

    scope = token.get("scope")

    if isinstance(scope, str):
        oauth_token.scopes = scope
    elif isinstance(scope, list):
        oauth_token.scopes = " ".join(str(item) for item in scope)

    database.commit()
    database.refresh(user)

    request.session["user_id"] = user.id

    return GoogleOAuthCallbackResponse(
        connected=True,
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
    )


@router.get(
    "/status",
    response_model=GoogleConnectionStatus,
)
def google_status(
    request: Request,
    database: Annotated[Session, Depends(get_db)],
) -> GoogleConnectionStatus:
    user_id = request.session.get("user_id")

    if not isinstance(user_id, int):
        return GoogleConnectionStatus(connected=False)

    statement = (
        select(User, OAuthToken)
        .join(
            OAuthToken,
            OAuthToken.user_id == User.id,
        )
        .where(
            User.id == user_id,
            OAuthToken.provider == "google",
        )
    )

    result = database.execute(statement).first()

    if result is None:
        return GoogleConnectionStatus(connected=False)

    user, oauth_token = result

    return GoogleConnectionStatus(
        connected=True,
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        expires_at=oauth_token.expires_at,
    )

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.oauth_token import OAuthToken
from app.models.user import User

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


def clear_data() -> None:
    with TestSessionLocal() as database:
        database.query(OAuthToken).delete()
        database.query(User).delete()
        database.commit()


def create_user(email: str = "user@example.com") -> int:
    with TestSessionLocal() as database:
        user = User(
            email=email,
            google_subject="google-user-123",
            display_name="Test User",
        )

        database.add(user)
        database.commit()
        database.refresh(user)

        return user.id


def test_user_can_store_google_oauth_token() -> None:
    clear_data()
    user_id = create_user()

    with TestSessionLocal() as database:
        token = OAuthToken(
            user_id=user_id,
            provider="google",
            access_token="access-token-value",
            refresh_token="refresh-token-value",
            token_type="Bearer",
            scopes="openid email https://www.googleapis.com/auth/gmail.readonly",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )

        database.add(token)
        database.commit()
        database.refresh(token)

        assert token.id is not None
        assert token.user_id == user_id
        assert token.user.email == "user@example.com"
        assert token.user.oauth_token is not None
        assert token.user.oauth_token.id == token.id


def test_duplicate_user_email_is_rejected() -> None:
    clear_data()

    with TestSessionLocal() as database:
        database.add(
            User(
                email="duplicate@example.com",
                google_subject="google-user-1",
            )
        )
        database.commit()

        database.add(
            User(
                email="duplicate@example.com",
                google_subject="google-user-2",
            )
        )

        with pytest.raises(IntegrityError):
            database.commit()

        database.rollback()


def test_user_cannot_have_duplicate_provider_tokens() -> None:
    clear_data()
    user_id = create_user()

    with TestSessionLocal() as database:
        database.add(
            OAuthToken(
                user_id=user_id,
                provider="google",
                access_token="first-token",
            )
        )
        database.commit()

        database.add(
            OAuthToken(
                user_id=user_id,
                provider="google",
                access_token="second-token",
            )
        )

        with pytest.raises(IntegrityError):
            database.commit()

        database.rollback()

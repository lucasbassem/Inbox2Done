import pytest
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.config import Settings, settings
from app.core.token_encryption import decrypt_token, encrypt_token
from app.db.base import Base
from app.models.oauth_token import OAuthToken


def test_tokens_are_encrypted_in_storage_and_decrypted_on_read(monkeypatch):
    monkeypatch.setattr(settings, "token_encryption_key", Fernet.generate_key().decode())
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(OAuthToken(user_id=1, access_token="access-secret", refresh_token="refresh-secret"))
        db.commit()
        raw = db.execute(text("SELECT access_token, refresh_token FROM oauth_tokens")).first()
        assert "access-secret" not in raw[0]
        assert "refresh-secret" not in raw[1]
        token = db.get(OAuthToken, 1)
        assert token.access_token == "access-secret"
        assert token.refresh_token == "refresh-secret"
    engine.dispose()


def test_wrong_key_does_not_expose_or_accept_token(monkeypatch):
    monkeypatch.setattr(settings, "token_encryption_key", Fernet.generate_key().decode())
    value = encrypt_token("secret")
    monkeypatch.setattr(settings, "token_encryption_key", Fernet.generate_key().decode())
    with pytest.raises(InvalidToken):
        decrypt_token(value)


def test_production_rejects_insecure_configuration():
    with pytest.raises(ValueError):
        Settings(_env_file=None, app_env="production")
    config = Settings(
        _env_file=None,
        app_env="production",
        session_secret_key="a" * 40,
        token_encryption_key=Fernet.generate_key().decode(),
        frontend_origin="https://inbox.example.com",
        google_redirect_uri="https://inbox.example.com/api/auth/google/callback",
    )
    assert config.app_env == "production"


def test_production_rejects_legacy_plaintext(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "production")
    with pytest.raises(ValueError, match="Encrypt existing"):
        decrypt_token("plaintext")

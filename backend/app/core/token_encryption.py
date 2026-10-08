from cryptography.fernet import Fernet
from sqlalchemy import Text, TypeDecorator

from app.core.config import settings

PREFIX = "encrypted:v1:"


def encrypt_token(value: str | None) -> str | None:
    if value is None:
        return None
    if not settings.token_encryption_key:
        return value
    return PREFIX + Fernet(settings.token_encryption_key.encode()).encrypt(value.encode()).decode()


def decrypt_token(value: str | None) -> str | None:
    if value is None:
        return None
    if value.startswith(PREFIX):
        if not settings.token_encryption_key:
            raise ValueError(
                "TOKEN_ENCRYPTION_KEY is required to read encrypted OAuth credentials."
            )
        return (
            Fernet(settings.token_encryption_key.encode())
            .decrypt(value[len(PREFIX) :].encode())
            .decode()
        )
    if settings.app_env == "production":
        raise ValueError("Encrypt existing OAuth credentials before starting production.")
    return value


class EncryptedToken(TypeDecorator):
    """Encrypt stored credentials; callers only handle the decrypted token."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return encrypt_token(value)

    def process_result_value(self, value, dialect):
        return decrypt_token(value)

"""Run with `python -m scripts.encrypt_oauth_tokens` after configuring an encryption key.

Back up the database first; preserve the encryption key in your secret manager.
Existing encrypted values are verified, not encrypted twice. No token values are logged.
"""

from sqlalchemy import text

from app.core.config import settings
from app.core.token_encryption import PREFIX, decrypt_token, encrypt_token
from app.db.session import engine


def main():
    if not settings.token_encryption_key:
        raise SystemExit("Set TOKEN_ENCRYPTION_KEY before running this command.")
    count = 0
    with engine.begin() as connection:
        rows = connection.execute(
            text("SELECT id, access_token, refresh_token FROM oauth_tokens FOR UPDATE")
        ).mappings()
        for row in rows:
            values = {}
            for name in ("access_token", "refresh_token"):
                value = row[name]
                if value and value.startswith(PREFIX):
                    decrypt_token(value)
                    values[name] = value
                else:
                    values[name] = encrypt_token(value)
            connection.execute(
                text(
                    "UPDATE oauth_tokens SET access_token=:access_token, "
                    "refresh_token=:refresh_token WHERE id=:id"
                ),
                {"id": row["id"], **values},
            )
            count += 1
    print(f"Verified/encrypted credentials for {count} accounts.")


if __name__ == "__main__":
    main()

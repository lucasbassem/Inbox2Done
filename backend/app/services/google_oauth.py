from authlib.integrations.starlette_client import OAuth

from app.core.config import settings

GOOGLE_GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"

oauth = OAuth()

oauth.register(
    name="google",
    client_id=settings.google_client_id,
    client_secret=settings.google_client_secret,
    server_metadata_url=("https://accounts.google.com/.well-known/openid-configuration"),
    client_kwargs={
        "scope": (f"openid email profile {GOOGLE_GMAIL_READONLY_SCOPE}"),
    },
)

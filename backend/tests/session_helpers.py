import base64
import json

from itsdangerous import TimestampSigner

from app.core.config import settings


def session_cookie(user_id: int) -> str:
    data = base64.b64encode(json.dumps({"user_id": user_id}).encode())
    return TimestampSigner(settings.session_secret_key).sign(data).decode()

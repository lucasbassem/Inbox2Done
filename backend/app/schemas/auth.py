from datetime import datetime

from pydantic import BaseModel


class GoogleConnectionStatus(BaseModel):
    connected: bool
    user_id: int | None = None
    email: str | None = None
    display_name: str | None = None
    expires_at: datetime | None = None


class GoogleOAuthCallbackResponse(BaseModel):
    connected: bool
    user_id: int
    email: str
    display_name: str | None

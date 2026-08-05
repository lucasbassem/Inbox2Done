from pydantic import BaseModel


class GmailSyncResponse(BaseModel):
    user_id: int
    threads_fetched: int
    threads_created: int
    threads_updated: int
    messages_created: int
    messages_updated: int

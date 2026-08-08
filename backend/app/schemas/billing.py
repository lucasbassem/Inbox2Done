from pydantic import BaseModel


class BillingStatusResponse(BaseModel):
    plan: str
    daily_limit: int
    used_today: int
    remaining_today: int

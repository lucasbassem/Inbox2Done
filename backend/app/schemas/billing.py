from pydantic import BaseModel


class BillingStatusResponse(BaseModel):
    plan: str
    daily_limit: int
    used_today: int
    remaining_today: int
    checkout_available: bool = False
    portal_available: bool = False


class CheckoutSessionResponse(BaseModel):
    checkout_url: str

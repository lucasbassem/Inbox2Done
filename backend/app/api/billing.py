from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.db.session import get_db
from app.schemas.billing import BillingStatusResponse
from app.services.entitlements import get_thread_analysis_status


router = APIRouter(
    prefix="/api/billing",
    tags=["Billing"],
)


@router.get(
    "/status",
    response_model=BillingStatusResponse,
)
def get_billing_status(
    request: Request,
    database: Annotated[Session, Depends(get_db)],
) -> BillingStatusResponse:
    user_id = request.session.get("user_id")

    if not isinstance(user_id, int):
        raise AppError(
            status_code=401,
            error="authentication_required",
            message="Authentication is required.",
        )

    entitlement = get_thread_analysis_status(
        database,
        user_id,
    )

    return BillingStatusResponse(
        plan=entitlement.plan,
        daily_limit=entitlement.limit,
        used_today=entitlement.used,
        remaining_today=entitlement.remaining,
    )

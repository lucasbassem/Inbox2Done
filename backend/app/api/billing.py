from typing import Annotated

import stripe
from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.db.session import get_db
from app.models.subscription import Subscription
from app.schemas.billing import (
    BillingStatusResponse,
    CheckoutSessionResponse,
)
from app.services.entitlements import get_thread_analysis_status


router = APIRouter(
    prefix="/api/billing",
    tags=["Billing"],
)

settings = get_settings()


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


@router.post(
    "/checkout",
    response_model=CheckoutSessionResponse,
)
def create_checkout_session(
    request: Request,
    database: Annotated[Session, Depends(get_db)],
) -> CheckoutSessionResponse:
    user_id = request.session.get("user_id")

    if not isinstance(user_id, int):
        raise AppError(
            status_code=401,
            error="authentication_required",
            message="Authentication is required.",
        )

    if not settings.stripe_secret_key or not settings.stripe_pro_price_id:
        raise AppError(
            status_code=503,
            error="billing_not_configured",
            message="Billing is not configured.",
        )

    subscription = database.scalar(
        select(Subscription).where(
            Subscription.user_id == user_id
        )
    )

    if (
        subscription is not None
        and subscription.plan == "pro"
        and subscription.status in {"active", "trialing"}
    ):
        raise AppError(
            status_code=409,
            error="already_subscribed",
            message="You already have an active Pro subscription.",
        )

    stripe.api_key = settings.stripe_secret_key

    frontend_origin = settings.frontend_origin.rstrip("/")

    customer_parameters = {}

    if (
        subscription is not None
        and subscription.stripe_customer_id
    ):
        customer_parameters["customer"] = (
            subscription.stripe_customer_id
        )

    try:
        checkout_session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[
                {
                    "price": settings.stripe_pro_price_id,
                    "quantity": 1,
                }
            ],
            success_url=(
                f"{frontend_origin}/"
                "?checkout=success"
                "&session_id={CHECKOUT_SESSION_ID}"
            ),
            cancel_url=(
                f"{frontend_origin}/"
                "?checkout=cancelled"
            ),
            client_reference_id=str(user_id),
            metadata={
                "user_id": str(user_id),
            },
            subscription_data={
                "metadata": {
                    "user_id": str(user_id),
                }
            },
            **customer_parameters,
        )
    except stripe.StripeError as exc:
        raise AppError(
            status_code=502,
            error="stripe_checkout_failed",
            message="Could not create Stripe Checkout session.",
        ) from exc

    if not checkout_session.url:
        raise AppError(
            status_code=502,
            error="stripe_checkout_failed",
            message="Stripe did not return a Checkout URL.",
        )

    return CheckoutSessionResponse(
        checkout_url=checkout_session.url,
    )
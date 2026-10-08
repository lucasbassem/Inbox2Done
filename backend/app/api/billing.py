from datetime import UTC, datetime
from typing import Annotated

import stripe
from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import lock_job_owner, require_user_id
from app.core.config import get_settings
from app.core.exceptions import AppError
from app.db.session import get_db
from app.models.billing_event import BillingEvent
from app.models.subscription import Subscription
from app.models.user import User
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
    subscription = database.scalar(select(Subscription).where(Subscription.user_id == user_id))

    return BillingStatusResponse(
        plan=entitlement.plan,
        daily_limit=entitlement.limit,
        used_today=entitlement.used,
        remaining_today=entitlement.remaining,
        checkout_available=bool(
            settings.stripe_secret_key
            and settings.stripe_pro_price_id
            and settings.stripe_webhook_secret
        ),
        portal_available=bool(
            settings.stripe_secret_key and subscription and subscription.stripe_customer_id
        ),
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

    if (
        not settings.stripe_secret_key
        or not settings.stripe_pro_price_id
        or not settings.stripe_webhook_secret
    ):
        raise AppError(
            status_code=503,
            error="billing_not_configured",
            message="Billing is not configured.",
        )

    subscription = database.scalar(select(Subscription).where(Subscription.user_id == user_id))

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

    if subscription is not None and subscription.stripe_customer_id:
        customer_parameters["customer"] = subscription.stripe_customer_id

    try:
        checkout_session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[
                {
                    "price": settings.stripe_pro_price_id,
                    "quantity": 1,
                }
            ],
            success_url=(f"{frontend_origin}/?checkout=success&session_id={{CHECKOUT_SESSION_ID}}"),
            cancel_url=(f"{frontend_origin}/?checkout=cancelled"),
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
            idempotency_key=f"checkout-{user_id}-{int(datetime.now(UTC).timestamp()) // 1800}",
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


@router.post("/portal")
def create_billing_portal(request: Request, database: Annotated[Session, Depends(get_db)]):
    user_id = require_user_id(request)
    subscription = database.scalar(select(Subscription).where(Subscription.user_id == user_id))
    if not settings.stripe_secret_key or not subscription or not subscription.stripe_customer_id:
        raise AppError(
            status_code=404,
            error="billing_account_missing",
            message="No billing account is connected.",
        )
    try:
        portal = stripe.billing_portal.Session.create(
            api_key=settings.stripe_secret_key,
            customer=subscription.stripe_customer_id,
            return_url=settings.frontend_origin,
        )
    except stripe.StripeError as exc:
        raise AppError(
            status_code=502,
            error="billing_portal_failed",
            message="Billing portal is temporarily unavailable.",
        ) from exc
    return {"url": portal.url}


@router.post("/webhook")
async def stripe_webhook(request: Request, database: Annotated[Session, Depends(get_db)]):
    if not settings.stripe_webhook_secret or not settings.stripe_secret_key:
        raise AppError(
            status_code=503, error="billing_not_configured", message="Billing is not configured."
        )
    payload = await request.body()
    if len(payload) > 1_000_000:
        raise AppError(
            status_code=413, error="payload_too_large", message="Webhook payload is too large."
        )
    try:
        event = stripe.Webhook.construct_event(
            payload, request.headers.get("stripe-signature", ""), settings.stripe_webhook_secret
        ).to_dict()
    except (ValueError, stripe.SignatureVerificationError) as exc:
        raise AppError(
            status_code=400,
            error="invalid_webhook",
            message="Invalid webhook signature or payload.",
        ) from exc
    if database.get(BillingEvent, event["id"]):
        return {"received": True}
    event_type = event["type"]
    if event_type not in {
        "checkout.session.completed",
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
    }:
        return {"received": True}
    obj = event["data"]["object"]
    subscription_id = (
        obj.get("subscription") if event_type == "checkout.session.completed" else obj.get("id")
    )
    if not isinstance(subscription_id, str):
        return {"received": True}
    # Fetch canonical state rather than trusting a possibly delayed event snapshot.
    try:
        remote = stripe.Subscription.retrieve(
            subscription_id, api_key=settings.stripe_secret_key
        ).to_dict()
    except stripe.StripeError as exc:
        raise AppError(
            status_code=502,
            error="billing_sync_failed",
            message="Subscription sync failed; delivery can be retried.",
        ) from exc
    user_id = remote.get("metadata", {}).get("user_id", "")
    if not str(user_id).isdigit() or database.get(User, int(user_id)) is None:
        return {"received": True}
    user_id = int(user_id)
    lock_job_owner(database, user_id)
    if database.get(BillingEvent, event["id"]):
        return {"received": True}
    try:
        remote = stripe.Subscription.retrieve(
            subscription_id, api_key=settings.stripe_secret_key
        ).to_dict()
    except stripe.StripeError as exc:
        raise AppError(
            status_code=502,
            error="billing_sync_failed",
            message="Subscription sync failed; delivery can be retried.",
        ) from exc
    subscription = database.scalar(select(Subscription).where(Subscription.user_id == user_id))
    if subscription is None:
        subscription = Subscription(user_id=user_id, plan="free", status="active")
        database.add(subscription)
    if subscription.stripe_subscription_id not in {
        None,
        subscription_id,
    } and subscription.status in {"active", "trialing"}:
        database.add(BillingEvent(id=event["id"]))
        database.commit()
        return {"received": True}
    prices = [item.get("price", {}).get("id") for item in remote.get("items", {}).get("data", [])]
    status = remote.get("status", "canceled")
    subscription.plan = (
        "pro"
        if settings.stripe_pro_price_id in prices and status in {"active", "trialing"}
        else "free"
    )
    subscription.status = status
    subscription.stripe_customer_id = remote.get("customer")
    subscription.stripe_subscription_id = subscription_id
    ends = [item.get("current_period_end") for item in remote.get("items", {}).get("data", [])]
    end = remote.get("current_period_end") or next((value for value in ends if value), None)
    subscription.current_period_end = datetime.fromtimestamp(end, tz=UTC) if end else None
    database.add(BillingEvent(id=event["id"]))
    database.commit()
    return {"received": True}

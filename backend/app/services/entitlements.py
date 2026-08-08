from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.subscription import Subscription
from app.models.usage_event import UsageEvent


THREAD_ANALYSIS_EVENT = "thread_analysis"

FREE_DAILY_ANALYSIS_LIMIT = 1

# "Unlimited" to the customer, but with a high abuse-protection ceiling.
PRO_DAILY_ANALYSIS_LIMIT = 100


class UsageLimitExceeded(Exception):
    def __init__(
        self,
        *,
        plan: str,
        limit: int,
        used: int,
    ) -> None:
        self.plan = plan
        self.limit = limit
        self.used = used

        super().__init__(
            f"Daily {plan} analysis limit of {limit} has been reached."
        )


@dataclass(frozen=True)
class EntitlementResult:
    plan: str
    limit: int
    used: int
    remaining: int


def _utc_day_bounds(now: datetime) -> tuple[datetime, datetime]:
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    else:
        now = now.astimezone(UTC)

    start = now.replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )

    return start, start + timedelta(days=1)


def get_or_create_subscription(
    database: Session,
    user_id: int,
) -> Subscription:
    subscription = database.scalar(
        select(Subscription)
        .where(Subscription.user_id == user_id)
        .with_for_update()
    )

    if subscription is not None:
        return subscription

    subscription = Subscription(
        user_id=user_id,
        plan="free",
        status="active",
    )

    database.add(subscription)
    database.flush()

    return subscription


def get_daily_analysis_usage(
    database: Session,
    user_id: int,
    *,
    now: datetime | None = None,
) -> int:
    current_time = now or datetime.now(UTC)
    start, end = _utc_day_bounds(current_time)

    usage = database.scalar(
        select(
            func.coalesce(
                func.sum(UsageEvent.quantity),
                0,
            )
        ).where(
            UsageEvent.user_id == user_id,
            UsageEvent.event_type == THREAD_ANALYSIS_EVENT,
            UsageEvent.created_at >= start,
            UsageEvent.created_at < end,
        )
    )

    return int(usage or 0)


def consume_thread_analysis(
    database: Session,
    user_id: int,
    *,
    now: datetime | None = None,
) -> EntitlementResult:
    subscription = get_or_create_subscription(
        database,
        user_id,
    )

    is_pro = (
        subscription.plan == "pro"
        and subscription.status in {"active", "trialing"}
    )

    limit = (
        PRO_DAILY_ANALYSIS_LIMIT
        if is_pro
        else FREE_DAILY_ANALYSIS_LIMIT
    )

    used = get_daily_analysis_usage(
        database,
        user_id,
        now=now,
    )

    if used >= limit:
        raise UsageLimitExceeded(
            plan="pro" if is_pro else "free",
            limit=limit,
            used=used,
        )

    database.add(
        UsageEvent(
            user_id=user_id,
            event_type=THREAD_ANALYSIS_EVENT,
            quantity=1,
        )
    )

    database.flush()

    return EntitlementResult(
        plan="pro" if is_pro else "free",
        limit=limit,
        used=used + 1,
        remaining=max(limit - used - 1, 0),
    )
def get_thread_analysis_status(
        database: Session,
        user_id: int,
        *,
        now: datetime | None = None,
    ) -> EntitlementResult:
        subscription = database.scalar(
            select(Subscription).where(
                Subscription.user_id == user_id
            )
        )

        is_pro = (
            subscription is not None
            and subscription.plan == "pro"
            and subscription.status in {"active", "trialing"}
        )

        limit = (
            PRO_DAILY_ANALYSIS_LIMIT
            if is_pro
            else FREE_DAILY_ANALYSIS_LIMIT
        )

        used = get_daily_analysis_usage(
            database,
            user_id,
            now=now,
        )

        return EntitlementResult(
            plan="pro" if is_pro else "free",
            limit=limit,
            used=used,
            remaining=max(limit - used, 0),
        )
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import StaticPool, create_engine, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models.subscription import Subscription
from app.models.usage_event import UsageEvent
from app.models.user import User
from app.services.entitlements import (
    FREE_DAILY_ANALYSIS_LIMIT,
    PRO_DAILY_ANALYSIS_LIMIT,
    THREAD_ANALYSIS_EVENT,
    UsageLimitExceeded,
    consume_thread_analysis,
    get_daily_analysis_usage,
    get_thread_analysis_status,
)


@pytest.fixture
def database() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)

    with Session(engine) as session:
        user = User(email="entitlements@example.com")
        session.add(user)
        session.commit()
        session.refresh(user)
        session.info["user_id"] = user.id
        yield session

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_free_analysis_creates_subscription_and_usage_event(
    database: Session,
) -> None:
    user_id = database.info["user_id"]

    result = consume_thread_analysis(database, user_id)
    database.commit()

    subscription = database.scalar(select(Subscription).where(Subscription.user_id == user_id))
    event = database.scalar(select(UsageEvent).where(UsageEvent.user_id == user_id))

    assert result.plan == "free"
    assert result.limit == FREE_DAILY_ANALYSIS_LIMIT
    assert result.used == 1
    assert result.remaining == 0

    assert subscription is not None
    assert subscription.plan == "free"

    assert event is not None
    assert event.event_type == THREAD_ANALYSIS_EVENT
    assert event.quantity == 1


def test_free_analysis_rejects_second_use_on_same_day(
    database: Session,
) -> None:
    user_id = database.info["user_id"]
    now = datetime.now(UTC)

    consume_thread_analysis(database, user_id, now=now)
    database.commit()

    with pytest.raises(UsageLimitExceeded) as error:
        consume_thread_analysis(database, user_id, now=now)

    assert error.value.plan == "free"
    assert error.value.limit == FREE_DAILY_ANALYSIS_LIMIT
    assert error.value.used == 1


def test_active_pro_subscription_uses_pro_limit(
    database: Session,
) -> None:
    user_id = database.info["user_id"]

    database.add(
        Subscription(
            user_id=user_id,
            plan="pro",
            status="active",
        )
    )
    database.commit()

    result = consume_thread_analysis(database, user_id)

    assert result.plan == "pro"
    assert result.limit == PRO_DAILY_ANALYSIS_LIMIT
    assert result.used == 1
    assert result.remaining == PRO_DAILY_ANALYSIS_LIMIT - 1


def test_usage_count_only_includes_current_utc_day(
    database: Session,
) -> None:
    user_id = database.info["user_id"]
    now = datetime(2030, 5, 10, 12, tzinfo=UTC)

    database.add_all(
        [
            UsageEvent(
                user_id=user_id,
                event_type=THREAD_ANALYSIS_EVENT,
                quantity=2,
                created_at=now - timedelta(hours=1),
            ),
            UsageEvent(
                user_id=user_id,
                event_type=THREAD_ANALYSIS_EVENT,
                quantity=5,
                created_at=now - timedelta(days=1),
            ),
            UsageEvent(
                user_id=user_id,
                event_type="gmail_sync",
                quantity=8,
                created_at=now,
            ),
        ]
    )
    database.commit()

    assert get_daily_analysis_usage(database, user_id, now=now) == 2


def test_status_does_not_consume_usage(database: Session) -> None:
    user_id = database.info["user_id"]

    first = get_thread_analysis_status(database, user_id)
    second = get_thread_analysis_status(database, user_id)

    usage_events = database.scalars(select(UsageEvent).where(UsageEvent.user_id == user_id)).all()

    assert first == second
    assert first.plan == "free"
    assert first.used == 0
    assert first.remaining == FREE_DAILY_ANALYSIS_LIMIT
    assert usage_events == []

import hashlib
import hmac
import json
import time
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.api import billing
from app.models.billing_event import BillingEvent
from app.models.subscription import Subscription
from app.models.usage_event import UsageEvent
from app.worker.tasks.analysis import analyze_thread_task


@pytest.fixture
def stripe_config(monkeypatch):
    monkeypatch.setattr(billing.settings, "stripe_secret_key", "sk_test_fake")
    monkeypatch.setattr(billing.settings, "stripe_pro_price_id", "price_pro")
    monkeypatch.setattr(billing.settings, "stripe_webhook_secret", "whsec_test")


def signed_event(client, event):
    payload = json.dumps(event)
    timestamp = int(time.time())
    signature = hmac.new(
        b"whsec_test", f"{timestamp}.{payload}".encode(), hashlib.sha256
    ).hexdigest()
    return client.post(
        "/api/billing/webhook",
        content=payload,
        headers={
            "stripe-signature": f"t={timestamp},v1={signature}",
            "content-type": "application/json",
        },
    )


def test_webhook_requires_valid_signature(workflow, stripe_config):
    assert workflow.client.post("/api/billing/webhook", json={}).status_code == 400
    assert workflow.db.scalars(select(Subscription)).all() == []


def test_webhook_updates_paid_plan_idempotently_and_cancels(workflow, stripe_config, monkeypatch):
    remote = {
        "id": "sub_test",
        "status": "active",
        "customer": "cus_test",
        "metadata": {"user_id": "1"},
        "items": {"data": [{"price": {"id": "price_pro"}, "current_period_end": 1800000000}]},
    }
    monkeypatch.setattr(
        billing.stripe.Subscription,
        "retrieve",
        lambda *a, **kw: SimpleNamespace(to_dict=lambda: remote),
    )
    event = {
        "id": "evt_1",
        "type": "customer.subscription.updated",
        "data": {"object": {"id": "sub_test"}},
    }
    workflow.client.cookies.clear()  # Webhooks authenticate with signatures, not browser cookies.
    assert signed_event(workflow.client, event).status_code == 200
    assert signed_event(workflow.client, event).status_code == 200
    subscription = workflow.db.scalar(select(Subscription))
    assert subscription.plan == "pro"
    assert subscription.stripe_customer_id == "cus_test"
    assert len(workflow.db.scalars(select(BillingEvent)).all()) == 1
    remote["status"] = "canceled"
    event["id"] = "evt_2"
    assert signed_event(workflow.client, event).status_code == 200
    workflow.db.refresh(subscription)
    assert subscription.plan == "free"
    assert subscription.status == "canceled"


def test_unrelated_price_does_not_grant_pro(workflow, stripe_config, monkeypatch):
    monkeypatch.setattr(
        billing.stripe.Subscription,
        "retrieve",
        lambda *a, **kw: SimpleNamespace(
            to_dict=lambda: {
                "id": "sub_other",
                "status": "active",
                "customer": "cus_test",
                "metadata": {"user_id": "1"},
                "items": {"data": [{"price": {"id": "price_other"}}]},
            }
        ),
    )
    event = {
        "id": "evt_other",
        "type": "checkout.session.completed",
        "data": {"object": {"subscription": "sub_other"}},
    }
    assert signed_event(workflow.client, event).status_code == 200
    assert workflow.db.scalar(select(Subscription)).plan == "free"


def test_checkout_is_owned_and_portal_uses_stored_customer(workflow, stripe_config, monkeypatch):
    captured = {}

    def checkout(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(url="https://checkout.stripe.com/test")

    monkeypatch.setattr(billing.stripe.checkout.Session, "create", checkout)
    assert workflow.client.post("/api/billing/checkout").status_code == 200
    assert captured["client_reference_id"] == "1"
    assert captured["subscription_data"]["metadata"]["user_id"] == "1"
    assert workflow.db.scalars(select(Subscription)).all() == []
    workflow.db.add(
        Subscription(user_id=1, plan="pro", status="active", stripe_customer_id="cus_owner")
    )
    workflow.db.commit()

    def portal(**kwargs):
        assert kwargs["customer"] == "cus_owner"
        return SimpleNamespace(url="https://billing.stripe.com/test")

    monkeypatch.setattr(billing.stripe.billing_portal.Session, "create", portal)
    assert (
        workflow.client.post("/api/billing/portal").json()["url"]
        == "https://billing.stripe.com/test"
    )
    assert workflow.client.post("/api/billing/checkout").status_code == 409


def test_quota_is_enforced_and_queue_failure_refunds(workflow, monkeypatch):
    def fail(**_kwargs):
        raise ConnectionError("broker unavailable")

    monkeypatch.setattr(analyze_thread_task, "apply_async", fail)
    path = f"/api/threads/{workflow.thread.id}/analyze"
    assert workflow.client.post(path).status_code == 503
    assert workflow.db.scalars(select(UsageEvent)).all() == []
    monkeypatch.setattr(analyze_thread_task, "apply_async", lambda **kw: None)
    response = workflow.client.post(path)
    assert response.status_code == 202
    assert workflow.client.get("/api/billing/status").json()["remaining_today"] == 0

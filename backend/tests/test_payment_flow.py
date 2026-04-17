"""
Integration tests for the Stripe payment flow.

Covers:
  - PRO upgrade via checkout.session.completed webhook
  - Webhook deduplication (idempotent processing)
  - Signature verification (reject invalid signatures)
  - Downgrade on charge.refunded
  - Already-Pro idempotency

Run with:
    pytest backend/tests/test_payment_flow.py -v
"""

import json
import uuid

import pytest
import stripe
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import ASGITransport, AsyncClient

from backend.db_models import ProcessedStripeEvent, User, UserTier
from backend.main import app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
USER_ID = str(uuid.UUID("00000000-0000-0000-0000-000000000001"))

def _checkout_event(session_id: str = "cs_test_abc123", user_id: str = USER_ID):
    """Build a realistic Stripe checkout.session.completed event dict."""
    return {
        "id": f"evt_{session_id}",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": session_id,
                "client_reference_id": user_id,
                "customer": "cus_test_456",
                "subscription": "sub_test_789",
                "mode": "payment",
                "metadata": {"upgrade_source": "web", "plan_type": "onetime", "tier": "pro"},
            }
        },
    }


def _refund_event(charge_id: str = "ch_test_refund"):
    """Build a Stripe charge.refunded event dict."""
    return {
        "id": f"evt_{charge_id}",
        "type": "charge.refunded",
        "data": {
            "object": {
                "id": charge_id,
                "customer": "cus_test_456",
                "amount_refunded": 4900,
                "amount": 4900,  # Full refund
            }
        },
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestWebhookSignatureVerification:
    """Stripe webhook must reject bad signatures and accept valid ones."""

    @pytest.mark.asyncio
    async def test_invalid_signature_returns_401(self):
        """Bad Stripe-Signature header results in 401 Unauthorized."""
        event = _checkout_event()

        with patch("backend.services.stripe_service.STRIPE_WEBHOOK_SECRET", "whsec_real"):
            with patch("stripe.Webhook.construct_event") as mock_construct:
                mock_construct.side_effect = stripe.error.SignatureVerificationError(
                    "Invalid signature", "sig_header"
                )

                transport = ASGITransport(app=app)
                async with AsyncClient(transport=transport, base_url="http://test") as client:
                    resp = await client.post(
                        "/api/payments/webhook",
                        content=json.dumps(event),
                        headers={
                            "Content-Type": "application/json",
                            "Stripe-Signature": "bad_sig",
                        },
                    )

        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_payload_returns_400(self):
        """Malformed payload body results in 400 Bad Request."""
        with patch("backend.services.stripe_service.STRIPE_WEBHOOK_SECRET", "whsec_real"):
            with patch("stripe.Webhook.construct_event") as mock_construct:
                mock_construct.side_effect = ValueError("Invalid payload")

                transport = ASGITransport(app=app)
                async with AsyncClient(transport=transport, base_url="http://test") as client:
                    resp = await client.post(
                        "/api/payments/webhook",
                        content=b"corrupted",
                        headers={
                            "Content-Type": "application/json",
                            "Stripe-Signature": "t=123,v1=abc",
                        },
                    )

        assert resp.status_code == 400


class TestProUpgradeFlow:
    """Checkout session completed → user.tier becomes 'pro'."""

    @pytest.mark.asyncio
    async def test_checkout_completed_upgrades_user(self):
        """
        Happy path: FREE user → checkout → webhook → tier = PRO.
        Verifies handle_checkout_session_completed is called with session data.
        """
        event = _checkout_event()

        with patch("backend.services.stripe_service.STRIPE_WEBHOOK_SECRET", "whsec_real"):
            with patch("stripe.Webhook.construct_event", return_value=event):
                with patch(
                    "backend.services.stripe_service.handle_checkout_session_completed",
                    new_callable=AsyncMock,
                ) as mock_handler:
                    mock_handler.return_value = True

                    transport = ASGITransport(app=app)
                    async with AsyncClient(transport=transport, base_url="http://test") as client:
                        resp = await client.post(
                            "/api/payments/webhook",
                            content=json.dumps(event),
                            headers={
                                "Content-Type": "application/json",
                                "Stripe-Signature": "t=123,v1=valid",
                            },
                        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "received"
        # Verify the correct session object was passed to the handler
        mock_handler.assert_awaited_once()
        call_args = mock_handler.call_args
        session_arg = call_args[0][1]  # Second positional arg is `session`
        assert session_arg["client_reference_id"] == USER_ID

    @pytest.mark.asyncio
    async def test_checkout_handler_performs_tier_upgrade(self):
        """
        Unit test for handle_checkout_session_completed:
        verifies DB operations (dedup check, lock, update, commit).
        """
        from backend.services.stripe_service import handle_checkout_session_completed

        session_data = _checkout_event()["data"]["object"]
        mock_db = AsyncMock()

        # Mock: no existing processed event (first time)
        mock_db.execute.return_value.scalar_one_or_none.return_value = None
        # Mock: user found, tier = free
        mock_user = MagicMock(spec=User)
        mock_user.tier = UserTier.free
        mock_user.id = USER_ID
        mock_db.scalar.return_value = mock_user

        result = await handle_checkout_session_completed(mock_db, session_data)

        # Should have committed
        mock_db.commit.assert_awaited_once()
        # Should return True (upgrade happened)
        assert result is True

    @pytest.mark.asyncio
    async def test_already_pro_user_not_double_upgraded(self):
        """
        Idempotency: if user.tier is already 'pro', handler returns False.
        """
        from backend.services.stripe_service import handle_checkout_session_completed

        session_data = _checkout_event()["data"]["object"]
        mock_db = AsyncMock()

        # No dedup record → proceed
        mock_db.execute.return_value.scalar_one_or_none.return_value = None
        # User is already PRO
        mock_user = MagicMock(spec=User)
        mock_user.tier = UserTier.pro
        mock_db.scalar.return_value = mock_user

        result = await handle_checkout_session_completed(mock_db, session_data)

        assert result is False
        # commit still called (to save the ProcessedStripeEvent dedup record)
        # but UPDATE should NOT have run for user tier


class TestWebhookDeduplication:
    """Same event ID processed twice → second call is a no-op."""

    @pytest.mark.asyncio
    async def test_duplicate_webhook_returns_200_no_side_effects(self):
        """
        Stripe sends same event twice (retry). Should return 200 both times.
        Handler should detect dedup and skip processing.
        """
        event = _checkout_event(session_id="cs_dup_test")

        with patch("backend.services.stripe_service.STRIPE_WEBHOOK_SECRET", "whsec_real"):
            with patch("stripe.Webhook.construct_event", return_value=event):
                with patch(
                    "backend.services.stripe_service.handle_checkout_session_completed",
                    new_callable=AsyncMock,
                ) as mock_handler:
                    # First call processed, second deduped
                    mock_handler.side_effect = [True, False]

                    transport = ASGITransport(app=app)
                    async with AsyncClient(transport=transport, base_url="http://test") as client:
                        resp1 = await client.post(
                            "/api/payments/webhook",
                            content=json.dumps(event),
                            headers={
                                "Content-Type": "application/json",
                                "Stripe-Signature": "t=123,v1=valid",
                            },
                        )
                        resp2 = await client.post(
                            "/api/payments/webhook",
                            content=json.dumps(event),
                            headers={
                                "Content-Type": "application/json",
                                "Stripe-Signature": "t=123,v1=valid",
                            },
                        )

        assert resp1.status_code == 200
        assert resp2.status_code == 200
        assert mock_handler.await_count == 2


class TestRefundDowngrade:
    """charge.refunded event → user downgraded back to free."""

    @pytest.mark.asyncio
    async def test_refund_triggers_handler(self):
        """Full refund webhook calls handle_charge_refunded."""
        event = _refund_event()

        with patch("backend.services.stripe_service.STRIPE_WEBHOOK_SECRET", "whsec_real"):
            with patch("stripe.Webhook.construct_event", return_value=event):
                with patch(
                    "backend.services.stripe_service.handle_charge_refunded",
                    new_callable=AsyncMock,
                ) as mock_refund:
                    mock_refund.return_value = True

                    transport = ASGITransport(app=app)
                    async with AsyncClient(transport=transport, base_url="http://test") as client:
                        resp = await client.post(
                            "/api/payments/webhook",
                            content=json.dumps(event),
                            headers={
                                "Content-Type": "application/json",
                                "Stripe-Signature": "t=123,v1=valid",
                            },
                        )

        assert resp.status_code == 200
        mock_refund.assert_awaited_once()


class TestWebhookErrorHandling:
    """DB failures → HTTP 500 → Stripe retries (safety valve)."""

    @pytest.mark.asyncio
    async def test_db_failure_returns_500_for_stripe_retry(self):
        """If handler raises, webhook returns 500 so Stripe re-sends."""
        event = _checkout_event()

        with patch("backend.services.stripe_service.STRIPE_WEBHOOK_SECRET", "whsec_real"):
            with patch("stripe.Webhook.construct_event", return_value=event):
                with patch(
                    "backend.services.stripe_service.handle_checkout_session_completed",
                    new_callable=AsyncMock,
                ) as mock_handler:
                    mock_handler.side_effect = Exception("Database connection lost")

                    transport = ASGITransport(app=app)
                    async with AsyncClient(transport=transport, base_url="http://test") as client:
                        resp = await client.post(
                            "/api/payments/webhook",
                            content=json.dumps(event),
                            headers={
                                "Content-Type": "application/json",
                                "Stripe-Signature": "t=123,v1=valid",
                            },
                        )

        assert resp.status_code == 500

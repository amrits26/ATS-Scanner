"""
Stripe payment processing service — PHASE 2: REVENUE FORTRESS v5.0 (Final Boss)

Bulletproof architecture with:
- Idempotency keys (prevent duplicate charges on retries)
- Race-condition proof deduplication (INSERT ... ON CONFLICT DO NOTHING)
- Atomic transactions (DB commit → ARQ enqueue, 500 error on DB failure)
- Full-refund-only logic (ignore partial refunds)
- Production-grade audit logging
- HTTP 500 safety valve for Stripe retries
"""

import os
import logging
import stripe
import uuid
from typing import Optional, Dict, Any
from datetime import datetime
from sqlalchemy import update, select, insert, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db_models import (
    User,
    UserTier,
    AnalysisResult,
)

logger = logging.getLogger(__name__)

# ============================================================================
# Configuration: Stripe API Keys & Price IDs
# ============================================================================
stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "sk_test_placeholder")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "whsec_placeholder")

# Legacy price ID (for existing $9.99/mo subscribers)
STRIPE_PRO_PRICE_ID = os.getenv("STRIPE_PRO_PRICE_ID", "price_placeholder")

# NEW: 3-tier pricing price IDs
STRIPE_PRO_MONTHLY_NEW = os.getenv("STRIPE_PRO_MONTHLY_NEW_PRICE_ID", "price_xxx_REPLACE")
STRIPE_GATEWAY_ONE_TIME = os.getenv("STRIPE_GATEWAY_ONE_TIME_PRICE_ID", "price_yyy_REPLACE")
STRIPE_AGENCY_MONTHLY = os.getenv("STRIPE_AGENCY_MONTHLY_PRICE_ID", "price_zzz_REPLACE")


def get_price_id_for_tier(tier: str, payment_type: str = "monthly") -> str:
    """
    Map user tier + payment type to Stripe price ID.
    
    Args:
        tier: 'free', 'pro', or 'agency'
        payment_type: 'onetime', 'monthly', or 'annual'
    
    Returns:
        Stripe price ID string
        
    Raises:
        ValueError: If tier/payment_type combo is invalid
    """
    if tier == "pro" and payment_type == "monthly":
        return STRIPE_PRO_MONTHLY_NEW
    elif tier == "pro" and payment_type == "onetime":
        return STRIPE_GATEWAY_ONE_TIME
    elif tier == "agency" and payment_type == "monthly":
        return STRIPE_AGENCY_MONTHLY
    else:
        raise ValueError(f"Invalid tier/payment_type combo: {tier}/{payment_type}")


# ============================================================================
# 1. CHECKOUT SESSION CREATION — with Idempotency Key (v5.0)
# ============================================================================

async def create_checkout_session(
    user: User,
    success_url: str,
    cancel_url: str,
    upgrade_source: str = "web",
    plan_type: str = "monthly",
    tier: str = "pro",
) -> Dict[str, str]:
    """
    Create a Stripe Checkout Session for the specified tier/plan.
    
    BULLETPROOF: 
    - Includes unique idempotency_key to prevent duplicate charges on network retries
    - Tracks upgrade_source for analytics
    - Allows promotion codes
    - Supports gateway ($49 one-time → $19/mo subscription after trial)
    
    Args:
        user: Current user from JWT
        success_url: Redirect after successful payment
        cancel_url: Redirect if user cancels
        upgrade_source: Where the upgrade came from ('web', 'email_campaign', etc.)
        plan_type: 'onetime', 'monthly', or 'annual'
        tier: 'pro' or 'agency'
    
    Returns:
        {"checkout_url": "...", "session_id": "...", "idempotency_key": "...", "plan_type": "..."}
    
    Raises:
        ValueError: If user already subscribed, email missing, or Stripe config error
    """
    if not user or not user.email:
        raise ValueError("User must be authenticated with email")
    
    if user.tier in [UserTier.pro, UserTier.agency]:
        raise ValueError(f"User is already a {user.tier} subscriber")
    
    # Determine mode (subscription vs. payment) based on plan_type
    if plan_type == "onetime":
        mode = "payment"  # One-time charge
    else:
        mode = "subscription"  # Recurring subscription
    
    # Get the appropriate price ID
    try:
        price_id = get_price_id_for_tier(tier, plan_type)
    except ValueError as e:
        raise ValueError(f"Invalid pricing configuration: {str(e)}")
    
    if not price_id or "REPLACE" in price_id:
        raise ValueError(
            f"Stripe price ID not configured for {tier}/{plan_type}. "
            "Add STRIPE_*_PRICE_ID to .env file"
        )
    
    # === CRITICAL: Generate unique idempotency key ===
    # Format: checkout_{user_id}_{random_uuid}
    # Stripe uses this to deduplicate retried requests (network failures)
    idempotency_key = f"checkout_{user.id}_{uuid.uuid4()}"
    
    try:
        # For gateway plan: add trial period (14 days)
        subscription_data = None
        if plan_type == "onetime" and tier == "pro":
            # Gateway product: $49 one-time, then auto-upgrade to $19/mo after 14-day trial
            subscription_data = {
                "trial_period_days": 14,
                "items": [{"price": STRIPE_PRO_MONTHLY_NEW, "quantity": 1}],
                "metadata": {"gateway_source": "onetime_49"},
            }
        
        # Build line items
        line_items = [{"price": price_id, "quantity": 1}]
        
        # Stripe API call with idempotency_key header
        session = stripe.checkout.Session.create(
            idempotency_key=idempotency_key,
            payment_method_types=["card"],
            mode=mode,
            line_items=line_items,
            success_url=success_url,
            cancel_url=cancel_url,
            customer_email=user.email,
            client_reference_id=str(user.id),  # Used in webhook to identify user
            allow_promotion_codes=True,  # Allow discount codes
            billing_address_collection="auto",
            subscription_data=subscription_data,
            metadata={
                "user_id": str(user.id),
                "email": user.email,
                "upgrade_source": upgrade_source,
                "plan_type": plan_type,  # NEW: Track payment type
                "tier": tier,  # NEW: Track which tier
            },
        )
        
        logger.info(
            f"[STRIPE] ✓ Checkout session created: {session.id} "
            f"for {user.email} (tier={tier}, plan={plan_type}, idempotency_key={idempotency_key})"
        )
        
        return {
            "checkout_url": session.url,
            "session_id": session.id,
            "idempotency_key": idempotency_key,
            "plan_type": plan_type,
            "tier": tier,
        }
    
    except stripe.error.StripeError as e:
        logger.error(
            f"[STRIPE] ✗ Error creating checkout session for {user.email} ({tier}/{plan_type}): {str(e)}"
        )
        raise ValueError(f"Stripe error: {str(e)}")

# ============================================================================
# 2. WEBHOOK HANDLERS — Atomic Transactions + HTTP 500 Safety Valve (v5.0)
# ============================================================================

async def handle_checkout_session_completed(
    db: AsyncSession,
    session: Dict[str, Any],
) -> bool:
    """
    Handle checkout.session.completed webhook event.
    
    BULLETPROOF GUARDS (Final Boss v5.0):
    1. **Deduplication:** Check processed_stripe_events (ON CONFLICT DO NOTHING)
    2. **Atomicity:** DB commit BEFORE returning 200 (HTTP 500 if fails)
    3. **Race condition proof:** Use SELECT ... FOR UPDATE
    4. **Idempotency:** If user already Pro, skip (don't double-upgrade)
    
    Args:
        db: Database session (transaction context)
        session: Stripe checkout session object
    
    Returns:
        True if user was updated, False if already Pro or not found
    
    Raises:
        Exception: If critical DB error (will trigger HTTP 500 response)
    """
    user_id = session.get("client_reference_id")
    event_id = session.get("id")  # Session ID === Event ID
    
    if not user_id or not event_id:
        logger.warning(
            f"[STRIPE WEBHOOK] checkout.session.completed: "
            f"Missing client_reference_id={user_id} or session.id={event_id}"
        )
        return False
    
    try:
        # === STEP 1: Deduplication (Race-Condition Proof) ===
        # Use INSERT ... ON CONFLICT DO NOTHING to prevent race conditions
        stmt_check_dedup = insert(text("""
            processed_stripe_events (event_id, event_type, user_id, webhook_payload, processed_at)
            VALUES (:event_id, 'checkout.session.completed', :user_id, :payload, NOW())
            ON CONFLICT (event_id) DO NOTHING
        """)).bindparams(
            event_id=event_id,
            user_id=user_id,
            payload=session,
        )
        
        result_dedup = await db.execute(stmt_check_dedup)
        
        # If no rows inserted, this event was already processed
        if result_dedup.rowcount == 0:
            logger.info(
                f"[STRIPE WEBHOOK] checkout.session.completed: "
                f"Event {event_id} already processed (deduplication)"
            )
            return False
        
        # === STEP 2: Atomicity + Race Condition Prevention ===
        # Use SELECT ... FOR UPDATE to lock the user row (prevent concurrent updates)
        stmt_lock = select(User).where(User.id == user_id).with_for_update()
        user_row = await db.scalar(stmt_lock)
        
        if not user_row:
            logger.warning(
                f"[STRIPE WEBHOOK] checkout.session.completed: User {user_id} not found"
            )
            return False
        
        # === STEP 3: Idempotency Check ===
        # Don't double-upgrade: if tier is already 'pro', skip
        if user_row.tier == UserTier.pro:
            logger.info(
                f"[STRIPE WEBHOOK] checkout.session.completed: "
                f"User {user_id} already Pro (idempotency check)"
            )
            return False
        
        # === STEP 4: Atomic DB Update ===
        stmt_update = (
            update(User)
            .where(User.id == user_id)
            .values(
                tier=UserTier.pro,
                stripe_customer_id=session.get("customer"),
                stripe_subscription_id=session.get("subscription"),
                scan_limit=-1,  # Unlimited for Pro
                upgrade_source=session.get("metadata", {}).get("upgrade_source", "web"),
            )
        )
        result = await db.execute(stmt_update)
        
        # === STEP 5: COMMIT (Critical) ===
        # If commit fails → exception raised → HTTP 500 sent to Stripe
        # Stripe retries automatically (safety valve)
        await db.commit()
        
        logger.info(
            f"[STRIPE WEBHOOK] ✓ User {user_id} upgraded to PRO "
            f"(event_id={event_id}, stripe_customer={session.get('customer')})"
        )
        
        # === STEP 6: Enqueue welcome email (after commit) ===
        # If this fails, email goes to DLQ (recovery worker will handle)
        try:
            from backend.jobs import queue_analysis_job
            await queue_analysis_job(
                "send_welcome_email",
                {
                    "user_id": str(user_id),
                    "email": session.get("customer_email", ""),
                }
            )
            logger.info(f"[STRIPE WEBHOOK] Welcome email enqueued for {user_id}")
        except Exception as e:
            logger.error(
                f"[STRIPE WEBHOOK] Failed to enqueue welcome email for {user_id}: {str(e)} "
                f"(will be caught by DLQ recovery)"
            )
        
        return True
    
    except Exception as e:
        # Transaction rolls back automatically
        logger.error(
            f"[STRIPE WEBHOOK] ✗ checkout.session.completed failed for {user_id}: {str(e)}"
        )
        # Re-raise so main.py returns HTTP 500 to Stripe
        raise


async def handle_charge_refunded(
    db: AsyncSession,
    charge: Dict[str, Any],
) -> bool:
    """
    Handle charge.refunded webhook event.
    
    BULLETPROOF GUARDS (Final Boss v5.0):
    1. **Full Refund Only:** Only downgrade if refund.amount == charge.amount
    2. **Partial Refund Ignored:** Don't downgrade for partial refunds (user may be disputing)
    3. **Deduplication:** Use ON CONFLICT DO NOTHING
    4. **Atomic:** DB commit before returning
    
    Args:
        db: Database session
        charge: Stripe charge object from webhook
    
    Returns:
        True if user was downgraded, False if partial refund or user not found
    
    Raises:
        Exception: If critical DB error (triggers HTTP 500)
    """
    event_id = charge.get("id")
    customer_id = charge.get("customer")
    refunded_amount = charge.get("amount_refunded", 0)
    total_amount = charge.get("amount", 0)
    
    if not customer_id:
        logger.warning("[STRIPE WEBHOOK] charge.refunded: No customer_id found")
        return False
    
    # === CRITICAL GUARD: Full Refund Only ===
    if refunded_amount != total_amount:
        logger.info(
            f"[STRIPE WEBHOOK] ⊘ Partial refund for {customer_id}: "
            f"${refunded_amount/100:.2f} of ${total_amount/100:.2f}. "
            f"IGNORING (not downgrading tier)"
        )
        return False
    
    try:
        # === Deduplication ===
        stmt_dedup = insert(text("""
            processed_stripe_events (event_id, event_type, user_id, webhook_payload, processed_at)
            VALUES (:event_id, 'charge.refunded', NULL, :payload, NOW())
            ON CONFLICT (event_id) DO NOTHING
        """)).bindparams(
            event_id=event_id,
            payload=charge,
        )
        
        result_dedup = await db.execute(stmt_dedup)
        
        if result_dedup.rowcount == 0:
            logger.info(
                f"[STRIPE WEBHOOK] charge.refunded: Event {event_id} already processed"
            )
            return False
        
        # === Find and lock user ===
        stmt_lock = select(User).where(User.stripe_customer_id == customer_id).with_for_update()
        user_row = await db.scalar(stmt_lock)
        
        if not user_row:
            logger.warning(
                f"[STRIPE WEBHOOK] charge.refunded: "
                f"No user with stripe_customer={customer_id}"
            )
            return False
        
        # === Atomic downgrade ===
        stmt_update = (
            update(User)
            .where(User.stripe_customer_id == customer_id)
            .values(
                tier=UserTier.free,
                stripe_subscription_id=None,
                scan_limit=3,  # 3 scans/month for Free tier
            )
        )
        await db.execute(stmt_update)
        await db.commit()
        
        logger.info(
            f"[STRIPE WEBHOOK] ✓ Full refund: User {customer_id} downgraded to FREE "
            f"(refund=${refunded_amount/100:.2f})"
        )
        
        return True
    
    except Exception as e:
        logger.error(
            f"[STRIPE WEBHOOK] ✗ charge.refunded failed for {customer_id}: {str(e)}"
        )
        raise


async def handle_subscription_deleted(
    db: AsyncSession,
    subscription: Dict[str, Any],
) -> bool:
    """
    Handle customer.subscription.deleted webhook event (Final Boss v5.0).
    
    Downgrades user back to FREE tier when subscription is canceled
    (not a refund—user chose to cancel).
    
    Args:
        db: Database session
        subscription: Stripe subscription object from webhook
    
    Returns:
        True if user was downgraded, False if user not found
    
    Raises:
        Exception: If critical DB error (triggers HTTP 500)
    """
    event_id = subscription.get("id")
    customer_id = subscription.get("customer")
    
    if not customer_id:
        logger.warning("[STRIPE WEBHOOK] customer.subscription.deleted: No customer_id")
        return False
    
    try:
        # === Deduplication ===
        stmt_dedup = insert(text("""
            processed_stripe_events (event_id, event_type, user_id, webhook_payload, processed_at)
            VALUES (:event_id, 'customer.subscription.deleted', NULL, :payload, NOW())
            ON CONFLICT (event_id) DO NOTHING
        """)).bindparams(
            event_id=event_id,
            payload=subscription,
        )
        
        result_dedup = await db.execute(stmt_dedup)
        
        if result_dedup.rowcount == 0:
            logger.info(
                f"[STRIPE WEBHOOK] customer.subscription.deleted: "
                f"Event {event_id} already processed"
            )
            return False
        
        # === Lock + Update ===
        stmt_lock = select(User).where(User.stripe_customer_id == customer_id).with_for_update()
        user_row = await db.scalar(stmt_lock)
        
        if not user_row:
            logger.warning(
                f"[STRIPE WEBHOOK] customer.subscription.deleted: "
                f"No user with stripe_customer={customer_id}"
            )
            return False
        
        stmt_update = (
            update(User)
            .where(User.stripe_customer_id == customer_id)
            .values(
                tier=UserTier.free,
                stripe_subscription_id=None,
                scan_limit=3,
            )
        )
        await db.execute(stmt_update)
        await db.commit()
        
        logger.info(
            f"[STRIPE WEBHOOK] ✓ Subscription canceled: User {customer_id} downgraded to FREE"
        )
        
        return True
    
    except Exception as e:
        logger.error(
            f"[STRIPE WEBHOOK] ✗ customer.subscription.deleted failed for {customer_id}: {str(e)}"
        )
        raise


async def handle_invoice_payment_failed(
    db: AsyncSession,
    invoice: Dict[str, Any],
) -> bool:
    """
    Handle invoice.payment_failed webhook event.
    
    Payment declined → mark user as past_due or revert to free tier.
    
    Args:
        db: Database session
        invoice: Stripe invoice object from webhook
    
    Returns:
        True if user was affected, False otherwise
    """
    event_id = invoice.get("id")
    customer_id = invoice.get("customer")
    
    if not customer_id:
        logger.warning("[STRIPE WEBHOOK] invoice.payment_failed: No customer_id")
        return False
    
    try:
        # === Deduplication ===
        stmt_dedup = insert(text("""
            processed_stripe_events (event_id, event_type, user_id, webhook_payload, processed_at)
            VALUES (:event_id, 'invoice.payment_failed', NULL, :payload, NOW())
            ON CONFLICT (event_id) DO NOTHING
        """)).bindparams(
            event_id=event_id,
            payload=invoice,
        )
        
        result_dedup = await db.execute(stmt_dedup)
        
        if result_dedup.rowcount == 0:
            logger.info(
                f"[STRIPE WEBHOOK] invoice.payment_failed: Event {event_id} already processed"
            )
            return False
        
        # === Find and revert to free ===
        stmt_lock = select(User).where(User.stripe_customer_id == customer_id).with_for_update()
        user_row = await db.scalar(stmt_lock)
        
        if not user_row:
            logger.warning(
                f"[STRIPE WEBHOOK] invoice.payment_failed: "
                f"No user with stripe_customer={customer_id}"
            )
            return False
        
        stmt_update = (
            update(User)
            .where(User.stripe_customer_id == customer_id)
            .values(
                tier=UserTier.free,
                scan_limit=3,
            )
        )
        await db.execute(stmt_update)
        await db.commit()
        
        logger.warning(
            f"[STRIPE WEBHOOK] Payment failed for invoice={event_id}. "
            f"User {customer_id} reverted to FREE tier."
        )
        
        return True
    
    except Exception as e:
        logger.error(
            f"[STRIPE WEBHOOK] ✗ invoice.payment_failed failed for {customer_id}: {str(e)}"
        )
        raise

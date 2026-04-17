"""
Payment routes for Stripe integration.

Endpoints:
  POST /api/payments/subscribe - Create Stripe Checkout session
  POST /api/payments/webhook - Stripe webhook handler
  GET /api/payments/subscription-status - Get user's subscription
  GET /api/payments/prices - Get available pricing tiers
"""

import logging
import os
from datetime import datetime
from typing import Optional, List

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..db_models import User, ReferralConversion
from .auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/payments", tags=["payments"])

# Initialize Stripe
stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")

# Price IDs from environment
PRICES = {
    "pro_monthly": os.getenv("STRIPE_PRO_MONTHLY_PRICE_ID", ""),
    "pro_annual": os.getenv("STRIPE_PRO_ANNUAL_PRICE_ID", ""),
    "premium_monthly": os.getenv("STRIPE_PREMIUM_MONTHLY_PRICE_ID", ""),
    "premium_annual": os.getenv("STRIPE_PREMIUM_ANNUAL_PRICE_ID", ""),
}

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")


# ================================================================
# Pydantic Models
# ================================================================

class SubscribeRequest(BaseModel):
    """Request to create subscription"""
    tier: str = Field(..., pattern="^(pro|premium)$")
    plan_type: str = Field(..., pattern="^(monthly|annual)$")
    success_url: Optional[str] = None
    cancel_url: Optional[str] = None


class SubscribeResponse(BaseModel):
    """Subscription checkout response"""
    checkout_url: str
    session_id: str


class SubscriptionStatusResponse(BaseModel):
    """Current subscription status"""
    tier: str
    status: str
    renewal_date: Optional[datetime] = None
    scans_used: int
    scan_limit: int


class PriceInfo(BaseModel):
    """Pricing tier info"""
    tier: str
    plan_type: str
    price: float
    price_id: str
    features: List[str]


# ================================================================
# Subscription Routes
# ================================================================

@router.post("/subscribe", response_model=SubscribeResponse)
async def create_subscription(
    request: SubscribeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Create Stripe Checkout session for subscription.
    
    Returns URL to redirect user for payment.
    """
    try:
        # Get price ID
        price_key = f"{request.tier}_{request.plan_type}"
        price_id = PRICES.get(price_key)
        
        if not price_id:
            raise HTTPException(status_code=400, detail=f"Invalid tier/plan: {price_key}")
        
        # Create or get Stripe customer
        if not current_user.stripe_customer_id:
            customer = stripe.Customer.create(
                email=current_user.email,
                metadata={"user_id": str(current_user.id)}
            )
            current_user.stripe_customer_id = customer.id
            await db.commit()
        
        # Create checkout session
        success_url = request.success_url or f"{FRONTEND_URL}/dashboard?payment=success"
        cancel_url = request.cancel_url or f"{FRONTEND_URL}/pricing?payment=canceled"
        
        session = stripe.checkout.Session.create(
            customer=current_user.stripe_customer_id,
            payment_method_types=["card"],
            line_items=[{
                "price": price_id,
                "quantity": 1,
            }],
            mode="subscription",
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={
                "user_id": str(current_user.id),
                "tier": request.tier,
            },
            subscription_data={
                "metadata": {
                    "user_id": str(current_user.id),
                    "tier": request.tier,
                }
            }
        )
        
        logger.info(f"[PAYMENT] Checkout created for {current_user.email} - {request.tier}")
        
        return SubscribeResponse(
            checkout_url=session.url,
            session_id=session.id
        )
        
    except stripe.error.StripeError as e:
        logger.error(f"[PAYMENT] Stripe error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[PAYMENT] Failed: {e}")
        raise HTTPException(status_code=500, detail="Payment setup failed")


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Handle Stripe webhook events.
    
    Processes: customer.subscription.created, customer.subscription.deleted,
    invoice.payment_succeeded, invoice.payment_failed
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, webhook_secret
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")
    
    # Handle events in background to respond quickly
    background_tasks.add_task(process_stripe_event, event, db)
    
    return {"status": "received"}


async def process_stripe_event(event: dict, db: AsyncSession):
    """Process Stripe event and update database"""
    event_type = event["type"]
    data = event["data"]["object"]
    
    logger.info(f"[WEBHOOK] Processing {event_type}")
    
    if event_type == "customer.subscription.created":
        await handle_subscription_created(data, db)
    elif event_type == "customer.subscription.deleted":
        await handle_subscription_deleted(data, db)
    elif event_type == "customer.subscription.updated":
        await handle_subscription_updated(data, db)
    elif event_type == "invoice.payment_succeeded":
        await handle_payment_succeeded(data, db)
    elif event_type == "invoice.payment_failed":
        await handle_payment_failed(data, db)


async def handle_subscription_created(subscription: dict, db: AsyncSession):
    """Activate user subscription"""
    user_id = subscription.get("metadata", {}).get("user_id")
    if not user_id:
        return
    
    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    
    if user:
        tier = subscription.get("metadata", {}).get("tier", "pro")
        user.tier = tier
        user.subscription_status = "active"
        user.stripe_subscription_id = subscription["id"]
        user.scan_limit = 999999  # Unlimited for paid tiers
        user.subscription_end_date = datetime.fromtimestamp(subscription["current_period_end"])
        await db.commit()
        logger.info(f"[WEBHOOK] Activated {tier} for user {user.email}")


async def handle_subscription_deleted(subscription: dict, db: AsyncSession):
    """Downgrade user to free tier"""
    user_id = subscription.get("metadata", {}).get("user_id")
    if not user_id:
        return
    
    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    
    if user:
        user.tier = "free"
        user.subscription_status = "canceled"
        user.scan_limit = 3  # Reset to free tier limit
        user.scans_this_month = 0
        await db.commit()
        logger.info(f"[WEBHOOK] Downgraded to free for user {user.email}")


async def handle_subscription_updated(subscription: dict, db: AsyncSession):
    """Update subscription status"""
    user_id = subscription.get("metadata", {}).get("user_id")
    if not user_id:
        return
    
    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    
    if user:
        user.subscription_status = subscription["status"]
        user.subscription_end_date = datetime.fromtimestamp(subscription["current_period_end"])
        await db.commit()


async def handle_payment_succeeded(invoice: dict, db: AsyncSession):
    """Record successful payment"""
    logger.info(f"[WEBHOOK] Payment succeeded for invoice {invoice['id']}")
    # Could add payment history table here


async def handle_payment_failed(invoice: dict, db: AsyncSession):
    """Handle failed payment"""
    subscription_id = invoice.get("subscription")
    if subscription_id:
        stmt = select(User).where(User.stripe_subscription_id == subscription_id)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if user:
            user.subscription_status = "past_due"
            await db.commit()
            logger.warning(f"[WEBHOOK] Payment failed for user {user.email}")


# ================================================================
# Status Routes
# ================================================================

@router.get("/subscription-status", response_model=SubscriptionStatusResponse)
async def get_subscription_status(
    current_user: User = Depends(get_current_user),
):
    """Get current user's subscription status"""
    return SubscriptionStatusResponse(
        tier=current_user.tier,
        status=current_user.subscription_status or "inactive",
        renewal_date=current_user.subscription_end_date,
        scans_used=current_user.scans_this_month,
        scan_limit=current_user.scan_limit if current_user.scan_limit > 0 else 3
    )


@router.get("/prices", response_model=List[PriceInfo])
async def get_prices():
    """Get available pricing tiers"""
    return [
        PriceInfo(
            tier="free",
            plan_type="monthly",
            price=0,
            price_id="",
            features=["3 scans/month", "Basic match score", "Manual resume upload"]
        ),
        PriceInfo(
            tier="pro",
            plan_type="monthly",
            price=14.95,
            price_id=PRICES["pro_monthly"],
            features=["Unlimited scans", "Semantic matching", "Missing signals", "1-click auto-optimize", "Job application tracker"]
        ),
        PriceInfo(
            tier="pro",
            plan_type="annual",
            price=119.60,
            price_id=PRICES["pro_annual"],
            features=["Everything in Pro Monthly", "20% discount", "Priority support"]
        ),
        PriceInfo(
            tier="premium",
            plan_type="monthly",
            price=29.95,
            price_id=PRICES["premium_monthly"],
            features=["Everything in Pro", "AI bullet rewriting", "Cover letter generator", "Visa sponsorship insights", "Priority support"]
        ),
        PriceInfo(
            tier="premium",
            plan_type="annual",
            price=239.60,
            price_id=PRICES["premium_annual"],
            features=["Everything in Premium Monthly", "20% discount"]
        ),
    ]

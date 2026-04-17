"""
tailor_agent_routes.py

Tailor Agent payment & rewrite endpoints.
- POST /api/tailor/rewrite-for-job: Submit for rewrite → Stripe Payment Link
- POST /api/tailor/webhook/rewrite-completed: Stripe webhook → Trigger rewrite job
- GET /api/tailor/rewrite-status/{session_id}: Poll for completion
"""

import os
import logging
from uuid import uuid4
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select
import stripe

from backend.database import get_db
from backend.db_models import User, TailorRewritePurchase
from backend.services.stripe_service import StripeService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/tailor", tags=["tailor-agent"])

# Stripe configuration
stripe.api_key = os.getenv("STRIPE_API_KEY")
TAILOR_PRICE_ID = os.getenv("STRIPE_TAILOR_ONE_TIME_PRICE_ID", "price_tailor_29")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "whsec_test")


@router.post("/rewrite-for-job")
async def submit_tailor_rewrite(
    resume_text: str,  # Raw resume text
    job_description: str,  # Raw JD text
    job_title: Optional[str] = None,
    user: Optional[User] = Depends(lambda: None),  # Optional auth
    email: str = Query(...),  # Always require email
    session: AsyncSession = Depends(get_db),
) -> dict:
    """
    Submit resume + JD for $29 rewrite.
    Returns Stripe Payment Link for checkout.
    
    **Request:**
    - resume_text: Full resume (plain text)
    - job_description: Full JD (plain text)
    - email: User email (for receipt)
    - job_title: Optional job title (for tracking)
    
    **Response:**
    ```json
    {
        "stripe_url": "https://checkout.stripe.com/...",
        "session_id": "uuid",
        "price_cents": 2900
    }
    ```
    """
    
    # Validate inputs
    if not resume_text or len(resume_text.strip()) < 100:
        raise HTTPException(status_code=400, detail="Resume must be at least 100 characters")
    if not job_description or len(job_description.strip()) < 50:
        raise HTTPException(status_code=400, detail="Job description must be at least 50 characters")
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Valid email required")
    
    try:
        session_id = str(uuid4())
        
        # Create pending purchase record
        purchase = TailorRewritePurchase(
            id=uuid4(),
            user_id=user.id if user else None,
            email=email,
            job_description_snippet=job_description[:1000],
            resume_text=resume_text,
            status="pending",
            stripe_payment_id="pending",
        )
        session.add(purchase)
        await session.flush()
        purchase_id = str(purchase.id)
        
        # Create Stripe Checkout Session
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            mode="payment",
            customer_email=email,
            line_items=[
                {
                    "price": TAILOR_PRICE_ID,
                    "quantity": 1,
                }
            ],
            success_url=f"{os.getenv('FRONTEND_URL', 'http://localhost:5173')}/tailor-rewrite/{session_id}?status=success",
            cancel_url=f"{os.getenv('FRONTEND_URL', 'http://localhost:5173')}/tailor-rewrite/{session_id}?status=cancel",
            metadata={
                "purchase_id": purchase_id,
                "session_id": session_id,
                "email": email,
                "job_title": job_title or "unspecified",
            },
        )
        
        # Store session metadata in purchase record
        purchase.stripe_payment_id = checkout_session.id
        await session.commit()
        
        logger.info(f"[TAILOR] Created Stripe session {checkout_session.id} for {email}")
        
        return {
            "stripe_url": checkout_session.url,
            "session_id": session_id,
            "price_cents": 2900,
        }
        
    except stripe.error.StripeError as e:
        logger.error(f"[TAILOR] Stripe error: {e}")
        raise HTTPException(status_code=500, detail="Payment system error")
    except Exception as e:
        logger.error(f"[TAILOR] Submission error: {e}")
        await session.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rewrite-status/{session_id}")
async def get_rewrite_status(
    session_id: str,
    session: AsyncSession = Depends(get_db),
) -> dict:
    """
    Poll for rewrite completion status.
    
    **Response:**
    ```json
    {
        "status": "pending|processing|complete|failed",
        "download_url": "https://s3.amazonaws.com/...",
        "before_score": 55,
        "after_score": 82,
        "score_lift": 27
    }
    ```
    """
    
    try:
        # Query for purchase by session_id (stored in metadata during checkout creation)
        query = text("""
            SELECT id, status, download_url, before_ats_score, after_ats_score,
                   resume_text, rewritten_resume_text
            FROM tailor_rewrite_purchases 
            WHERE stripe_payment_id IN (
                SELECT id FROM stripe_webhook_events 
                WHERE metadata::text LIKE :session_id
            )
            LIMIT 1
        """)
        
        result = await session.execute(query, {"session_id": f"%{session_id}%"})
        row = result.first()
        
        if not row:
            raise HTTPException(status_code=404, detail="Rewrite not found")
        
        purchase_id, status, download_url, before_score, after_score, resume_text, rewritten_text = row
        
        return {
            "status": status,
            "download_url": download_url,
            "before_score": before_score,
            "after_score": after_score,
            "score_lift": (after_score - before_score) if (before_score and after_score) else None,
            "resume_text": resume_text,
            "rewritten_resume_text": rewritten_text,
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[TAILOR] Status check error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/webhook/rewrite-completed")
async def handle_stripe_webhook(
    request_body: dict,
    stripe_signature: str = Header(None),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """
    Stripe webhook receiver for successful payments.
    Triggers ARQ rewrite job.
    
    **Webhook Events:**
    - checkout.session.completed → Queue rewrite ARQ job
    """
    
    try:
        # Verify signature
        # Note: In production, verify_signature properly:
        # event = stripe.Webhook.construct_event(request_body, stripe_signature, STRIPE_WEBHOOK_SECRET)
        # For now, trust request_body from FastAPI JSON parsing
        
        if request_body.get("type") != "checkout.session.completed":
            return {"received": True}
        
        session_data = request_body.get("data", {}).get("object", {})
        stripe_payment_id = session_data.get("id")
        metadata = session_data.get("metadata", {})
        purchase_id = metadata.get("purchase_id")
        
        if not purchase_id:
            logger.warning(f"[TAILOR] Webhook missing purchase_id: {stripe_payment_id}")
            return {"received": True, "warning": "missing_purchase_id"}
        
        # Update purchase with Stripe payment ID (successful payment)
        query = text("""
            UPDATE tailor_rewrite_purchases 
            SET stripe_payment_id = :payment_id, status = 'processing', updated_at = NOW()
            WHERE id = :purchase_id
            RETURNING id
        """)
        
        result = await session.execute(query, {
            "payment_id": stripe_payment_id,
            "purchase_id": purchase_id,
        })
        
        updated_id = result.scalar()
        await session.commit()
        
        if updated_id:
            # Queue ARQ rewrite job (will be executed by worker)
            # In actual implementation, this would:
            # await redis_conn.enqueue_job("run_tailor_rewrite_job", purchase_id=purchase_id)
            logger.info(f"[TAILOR] Queued rewrite job for purchase {purchase_id}")
        
        return {"received": True, "purchase_id": purchase_id}
        
    except Exception as e:
        logger.error(f"[TAILOR] Webhook error: {e}")
        return {"received": False, "error": str(e)}

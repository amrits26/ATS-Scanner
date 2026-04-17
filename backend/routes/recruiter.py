"""
Recruiter API Routes
Handles lead listings, unlock purchases, hire reporting, and stats.
"""
import uuid
import stripe
import os
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from pydantic import BaseModel
from typing import Optional, List
import logging

from backend.database import get_db
from backend.auth import get_current_recruiter
from backend.db_models import RecruiterAccount
from backend.services.recruiter_service import (
    get_available_leads,
    get_recruiter_stats,
    get_unlocked_candidate,
    get_active_candidates_count,
    log_scarcity_event,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/recruiter", tags=["recruiter"])

# Stripe setup
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
LEAD_UNLOCK_PRICE_ID = os.getenv("STRIPE_LEAD_UNLOCK_PRICE_ID", "price_placeholder")


class UnlockRequest(BaseModel):
    pass


class HireReportRequest(BaseModel):
    candidate_id: str
    hire_date: Optional[str] = None  # YYYY-MM-DD


@router.get("/leads")
async def list_leads(
    current_recruiter: RecruiterAccount = Depends(get_current_recruiter),
    skills: Optional[str] = Query(None, description="Comma-separated skills"),
    location_state: Optional[str] = None,
    min_score: float = 85,
    days_old: int = 30,
    page: int = 1,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """Get paginated list of available leads for a recruiter."""
    try:
        recruiter_email = current_recruiter.email
        skills_list = skills.split(",") if skills else None
        result = await get_available_leads(
            db, recruiter_email, skills_list, location_state, min_score, days_old, page, limit
        )
        return result
    except Exception as e:
        logger.error(f"[RECRUITER] Error listing leads: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to load leads")


@router.post("/unlock/{candidate_id}")
async def create_unlock_checkout(
    candidate_id: str,
    current_recruiter: RecruiterAccount = Depends(get_current_recruiter),
    db: AsyncSession = Depends(get_db),
):
    """Create Stripe Checkout session for $5 lead unlock."""
    try:
        recruiter_email = current_recruiter.email
        # Check if already unlocked by this recruiter
        check_query = text("""
            SELECT status, expires_at FROM recruiter_unlock_purchases
            WHERE candidate_id = :candidate_id AND recruiter_email = :email
        """)
        existing = await db.execute(
            check_query, {"candidate_id": candidate_id, "email": recruiter_email}
        )
        row = existing.fetchone()
        if row:
            status_val = row[0]
            expires_at = row[1]
            if status_val == "completed" and expires_at and expires_at > datetime.utcnow():
                raise HTTPException(status_code=400, detail="Already unlocked and active")
            elif status_val == "pending":
                raise HTTPException(status_code=400, detail="Unlock already in progress")

        # Create Stripe Checkout Session
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price": LEAD_UNLOCK_PRICE_ID,
                "quantity": 1,
            }],
            mode="payment",
            success_url=f"{FRONTEND_URL}/recruiter?unlock_success=true&session_id={{CHECKOUT_SESSION_ID}}&candidate_id={candidate_id}",
            cancel_url=f"{FRONTEND_URL}/recruiter?unlock_canceled=true",
            metadata={
                "candidate_id": candidate_id,
                "recruiter_email": recruiter_email,
            }
        )

        # Record pending unlock
        insert_query = text("""
            INSERT INTO recruiter_unlock_purchases
            (candidate_id, recruiter_email, stripe_session_id, status, created_at)
            VALUES (:candidate_id, :email, :session_id, 'pending', NOW())
            ON CONFLICT (candidate_id, recruiter_email) DO NOTHING
        """)
        await db.execute(
            insert_query,
            {
                "candidate_id": candidate_id,
                "email": recruiter_email,
                "session_id": checkout_session.id,
            },
        )
        await db.commit()

        logger.info(f"[RECRUITER] Unlock checkout created for {recruiter_email}, candidate {candidate_id}")

        return {
            "sessionId": checkout_session.id,
            "checkoutUrl": checkout_session.url,
            "candidateId": candidate_id,
            "message": "Stripe checkout created. You'll have 90 days to contact this candidate."
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[RECRUITER] Stripe error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Stripe error: {str(e)}")


@router.post("/webhook")
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Handle Stripe webhook for successful payments."""
    try:
        payload = await request.body()
        sig_header = request.headers.get("stripe-signature")
        webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")

        event = stripe.Webhook.construct_event(
            payload, sig_header, webhook_secret
        )
    except ValueError as e:
        logger.warning(f"[RECRUITER] Invalid webhook payload: {str(e)}")
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError as e:
        logger.warning(f"[RECRUITER] Invalid webhook signature: {str(e)}")
        raise HTTPException(status_code=400, detail="Invalid signature")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        candidate_id = session.get("metadata", {}).get("candidate_id")
        recruiter_email = session.get("metadata", {}).get("recruiter_email")
        
        if candidate_id and recruiter_email:
            try:
                # Update unlock purchase to completed
                update_query = text("""
                    UPDATE recruiter_unlock_purchases
                    SET status = 'completed',
                        purchased_at = NOW(),
                        expires_at = NOW() + INTERVAL '90 days'
                    WHERE stripe_session_id = :session_id
                """)
                await db.execute(update_query, {"session_id": session["id"]})
                await db.commit()
                logger.info(f"[RECRUITER] Unlock completed for candidate {candidate_id}, recruiter {recruiter_email}")
            except Exception as e:
                logger.error(f"[RECRUITER] Error updating unlock: {str(e)}")
                await db.rollback()

    return {"status": "success"}


@router.post("/hire_report")
async def report_hire(
    req: HireReportRequest,
    current_recruiter: RecruiterAccount = Depends(get_current_recruiter),
    db: AsyncSession = Depends(get_db),
):
    """Recruiter reports a hire, triggers $500 charge."""
    try:
        recruiter_email = current_recruiter.email
        # Verify unlock exists and is active
        check_query = text("""
            SELECT id FROM recruiter_unlock_purchases
            WHERE candidate_id = :candidate_id
              AND recruiter_email = :email
              AND status = 'completed'
              AND expires_at > NOW()
        """)
        result = await db.execute(
            check_query, {"candidate_id": req.candidate_id, "email": recruiter_email}
        )
        if not result.fetchone():
            raise HTTPException(status_code=400, detail="No active unlock found for this candidate")

        # Check if hire already reported
        hire_check = text("""
            SELECT id FROM recruiter_hire_reports
            WHERE candidate_id = :candidate_id AND recruiter_email = :email
        """)
        existing = await db.execute(
            hire_check, {"candidate_id": req.candidate_id, "email": recruiter_email}
        )
        if existing.fetchone():
            raise HTTPException(status_code=400, detail="Hire already reported for this candidate")

        # Create Stripe charge for $500
        payment_intent = stripe.PaymentIntent.create(
            amount=50000,  # $500 in cents
            currency="usd",
            description=f"Hire success fee for candidate {req.candidate_id}",
            metadata={
                "candidate_id": req.candidate_id,
                "recruiter_email": recruiter_email,
            }
        )

        # Set status based on payment intent
        pay_status = "paid" if payment_intent.status == "succeeded" else "pending_payment"
        charge_id = payment_intent.id

        insert_query = text("""
            INSERT INTO recruiter_hire_reports
            (candidate_id, recruiter_email, hire_date, stripe_charge_id, status, amount_cents)
            VALUES (:candidate_id, :email, :hire_date, :charge_id, :status, 50000)
        """)
        await db.execute(
            insert_query,
            {
                "candidate_id": req.candidate_id,
                "email": recruiter_email,
                "hire_date": req.hire_date or datetime.utcnow().date(),
                "charge_id": charge_id,
                "status": pay_status,
            },
        )
        await db.commit()

        logger.info(f"[RECRUITER] Hire reported for candidate {req.candidate_id}, recruiter {recruiter_email}")

        return {"success": True, "message": "Hire reported successfully! $500 charge processed."}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[RECRUITER] Error reporting hire: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to report hire")


@router.get("/stats")
async def recruiter_stats(
    current_recruiter: RecruiterAccount = Depends(get_current_recruiter),
    db: AsyncSession = Depends(get_db),
):
    """Get recruiter stats."""
    try:
        stats = await get_recruiter_stats(db, current_recruiter.email)
        return stats
    except Exception as e:
        logger.error(f"[RECRUITER] Error fetching stats: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to load stats")


@router.get("/unlocked/{candidate_id}")
async def view_unlocked_candidate(
    candidate_id: str,
    current_recruiter: RecruiterAccount = Depends(get_current_recruiter),
    db: AsyncSession = Depends(get_db),
):
    """Get full candidate info after unlock."""
    try:
        candidate = await get_unlocked_candidate(db, candidate_id, current_recruiter.email)
        if not candidate:
            raise HTTPException(
                status_code=404,
                detail="Candidate not found or unlock expired/invalid"
            )
        return candidate
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[RECRUITER] Error fetching unlocked candidate: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to load candidate")


# =============================================================================
# PHASE 3: Recruiter Scarcity Feature - FOMO-based Conversion
# =============================================================================

@router.get("/candidates/count")
async def get_candidate_count(
    skills: Optional[str] = Query(None, description="Comma-separated skills"),
    location_state: Optional[str] = Query(None),
    min_score: Optional[int] = Query(85),
    current_recruiter: RecruiterAccount = Depends(get_current_recruiter),
    db: AsyncSession = Depends(get_db),
):
    """
    Return count of active candidates + scarcity messaging.
    Logs impression event for A/B analysis.
    
    Query params:
      - skills: CSV list (e.g., "python,javascript,aws")
      - location_state: State code (e.g., "CA", "NY")
      - min_score: Minimum ATS score (default 85)
    
    Returns:
        {
            'count': int,
            'message': str,
            'message_variant': str,
            'expires_soon_count': int
        }
    """
    try:
        recruiter_email = current_recruiter.email
        
        # Parse skills filter
        skills_list = None
        if skills:
            skills_list = [s.strip() for s in skills.split(",")]
        
        # Get count and scarcity data
        result = await get_active_candidates_count(
            db=db,
            recruiter_email=recruiter_email,
            skills=skills_list,
            location_state=location_state,
            min_score=min_score or 85,
        )
        
        # Log the impression event (for A/B analysis)
        if result["count"] > 0:
            try:
                await log_scarcity_event(
                    db=db,
                    recruiter_email=recruiter_email,
                    candidate_id="batch_view",
                    event_type="impression",
                    candidate_count=result["count"],
                    message_variant=result["message_variant"],
                )
            except Exception as e:
                logger.warning(f"[RECRUITER] Failed to log impression: {e}")
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[RECRUITER] Error fetching candidate count: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to load candidate count")

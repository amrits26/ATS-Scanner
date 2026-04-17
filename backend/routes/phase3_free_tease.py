"""
Phase 3: Free Tease Endpoint & Fear Loop Job Scheduler
GET /api/analyze/free - Free tier lightweight analysis
ARQ Job: schedule_fear_notification - 2h deferral + Stripe promo code
"""

import os
import json
import logging
from typing import Optional
from datetime import datetime, timedelta
import pytz
import asyncio
from fastapi import APIRouter, Depends, HTTPException, Form, UploadFile, File, BackgroundTasks, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import stripe

from backend.auth import verify_jwt_token, get_current_user
from backend.database import get_db
from backend.jobs import is_within_business_hours  # GAP 1: Import quiet hours check
from backend.services.percentile_helper import calculate_percentile_rank  # PHASE 1 FIX: Percentile calculation
from backend.services.free_teaser_service import (
    FreeTeaserService,
    save_free_scan,
    check_pro_user,
    calculate_resume_hash
)
from backend.utils.email_validator import validate_email
from backend.utils.idempotency import record_share_request

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Phase 3 Growth Engine"])

# GAP 5 FIX: Rate limiter for free tease endpoint (1 per 24 hours per email)
limiter = Limiter(key_func=get_remote_address)

# Initialize Gemini (from main.py injection)
GEMINI_CLIENT = None


def set_gemini_client(client):
    """Called from main.py during startup"""
    global GEMINI_CLIENT
    GEMINI_CLIENT = client


# ============================================================================
# POST /api/analyze/free - Free Tease Endpoint
# ============================================================================

@router.post("/analyze/free")
@limiter.limit("1/day")  # GAP 5 FIX: Enforce 24-hour cooldown per IP
async def analyze_free(
    request: Request,
    resume: UploadFile = File(...),
    jd: UploadFile = File(...),
    email: str = Form(...),
    timezone: str = Form("UTC"),
    consent: bool = Form(False),
    db: AsyncSession = Depends(get_db),
    background_tasks: BackgroundTasks = None
):
    """
    Free tier lightweight analysis (first 500 words each)
    Returns: ATS Score (1-100) + Top 3 Missing Keywords
    
    **NO AUTH REQUIRED** — This is lead capture
    
    Args:
        resume: Resume PDF/DOCX/TXT
        jd: Job description TXT
        email: User email
        timezone: Auto-detected timezone (e.g., 'America/New_York')
        consent: GDPR/CCPA checkbox (must be True)
    
    Returns:
        {
            "score": 72,
            "keywords": ["Machine Learning", "Docker", "CI/CD"],
            "promo_code": "FEAR20_ABC123",
            "expires_in_hours": 24,
            "message": "Upgrade to Pro for full optimization (20% off for 24h)"
        }
    
    Errors:
        - 403: Email belongs to Pro user
        - 400: Consent not given / Invalid email / Duplicate scan today
        - 429: Rate limited (1 per email per 24h)
        - 500: Gemini API error
    """
    try:
        # Step 1: Validate email
        is_valid, error_msg = validate_email(email)
        if not is_valid:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid email: {error_msg}"
            )
        
        # Step 2: Check consent (hard requirement)
        if not consent:
            raise HTTPException(
                status_code=400,
                detail="You must accept the terms to proceed"
            )
        
        # Step 3: Check if Pro user
        is_pro = await check_pro_user(db, email)
        if is_pro:
            raise HTTPException(
                status_code=403,
                detail="Pro users should use /api/analyze instead"
            )
        
        # Step 4: Read resume + JD
        resume_content = (await resume.read()).decode('utf-8', errors='ignore')
        jd_content = (await jd.read()).decode('utf-8', errors='ignore')
        
        if not resume_content or not jd_content:
            raise HTTPException(
                status_code=400,
                detail="Resume and JD files must not be empty"
            )
        
        # Step 5: Calculate resume hash (for deduplication)
        resume_hash = calculate_resume_hash(resume_content)
        
        # Step 6: Check idempotency (same resume same day?)
        is_duplicate, scans_remaining = await check_free_scan_idempotency(
            db, email, resume_hash
        )
        
        if is_duplicate:
            raise HTTPException(
                status_code=400,
                detail=f"You already scanned this resume today. Scans remaining: {scans_remaining}"
            )
        
        # Step 7: Gemini analysis (light-weight)
        teaser_service = FreeTeaserService(GEMINI_CLIENT)
        score, keywords = await teaser_service.analyze_free(
            resume_content,
            jd_content,
            email
        )
        
        # Step 8: Generate Stripe promo code
        promo_code = await teaser_service.create_stripe_promo_code(
            email,
            discount_percent=20,
            expiry_hours=24
        )
        
        # Step 9: Save to database
        scan_result = await save_free_scan(
            db,
            email=email,
            resume_hash=resume_hash,
            score=score,
            keywords=keywords,
            timezone=timezone,
            consent_given=True,
            promo_code=promo_code
        )
        
        if not scan_result:
            raise HTTPException(
                status_code=500,
                detail="Failed to save scan"
            )
        
        # Step 10: Schedule fear notification (if score < 55)
        if score < 55 and background_tasks:
            scan_id = scan_result.get("scan_id")
            background_tasks.add_task(
                schedule_fear_notification_job,
                db_session_factory=None,  # Will use get_db in job
                email=email,
                score=score,
                timezone=timezone,
                scan_id=scan_id,
                promo_code=promo_code
            )
        
        # Step 11: Log to PostHog
        background_tasks.add_task(
            log_posthog_event,
            db,
            event_type="free_scan_completed",
            email=email,
            metadata={
                "score": score,
                "timezone": timezone,
                "promo_code": promo_code
            }
        )
        
        # Step 12: Calculate percentile rank (PHASE 1 FIX: Include for free users too)
        percentile_rank = await calculate_percentile_rank(db, score)
        
        # Step 13: Return response with credibility signals
        return {
            "success": True,
            "score": score,
            "keywords": keywords,
            "percentile_rank": percentile_rank,  # PHASE 1 FIX: Now included for free tier
            "confidence_score": 70,  # Simple fixed confidence for free tier
            "promo_code": promo_code,
            "expires_in_hours": 24,
            "message": "Upgrade to Pro for full optimization (20% off for 24h)",
            "fear_email_scheduled": score < 55,
            "scans_remaining": scan_result.get("scans_remaining")
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Free analyze error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# TASK: schedule_fear_notification_job - 2h Deferral + Stripe Promo Code
# ============================================================================

async def schedule_fear_notification_job(
    db_session_factory,
    email: str,
    score: int,
    timezone: str,
    scan_id: str,
    promo_code: str,
    deferral_count: int = 0,
    max_deferrals: int = 5
):
    """
    ARQ Job: Schedule fear notification email
    
    Implements:
    - 2-hour deferral for scores < 55
    - Quiet hours enforcement (9 AM - 7 PM local time)
    - Max 5 deferrals (if exceeded, send anyway)
    
    Args:
        db_session_factory: AsyncSessionLocal factory
        email: User email
        score: ATS score
        timezone: User timezone (e.g., 'America/New_York')
        scan_id: Free scan ID
        promo_code: Stripe promo code
        deferral_count: Current deferral count
        max_deferrals: Max deferrals before force-send
    """
    try:
        # Get current time in user's timezone
        user_tz = pytz.timezone(timezone)
        now = datetime.now(user_tz)
        current_hour = now.hour
        
        # GAP 1 FIX: Use centralized quiet hours check from jobs.py
        in_quiet_hours = is_within_business_hours(timezone)
        
        # Calculate send time
        if not in_quiet_hours and deferral_count < max_deferrals:
            # Outside quiet hours, defer 1 hour
            send_at = datetime.now(user_tz) + timedelta(hours=1)
            logger.info(f"Fear email deferred (outside quiet hours): {email} → {send_at}")
            
            # Re-enqueue job for later
            # (In real implementation: arq.enqueue_job(..., at=send_at))
            return {
                "deferred": True,
                "reason": "outside_quiet_hours",
                "send_at": send_at.isoformat(),
                "deferral_count": deferral_count + 1
            }
        
        # Ready to send
        logger.info(f"Fear email sent: {email} (score={score}, deferral_count={deferral_count})")
        
        # Send email (via Resend or background queue)
        # TODO: Integrate with email_service.py send_fear_email()
        await send_fear_email(
            email=email,
            score=score,
            promo_code=promo_code,
            scan_id=scan_id
        )
        
        # Record in database
        if db_session_factory:
            async with db_session_factory() as db:
                stmt = text("""
                    UPDATE free_scans
                    SET fear_email_sent = TRUE, fear_email_sent_at = NOW()
                    WHERE id = :scan_id
                """)
                await db.execute(stmt, {"scan_id": scan_id})
                await db.commit()
        
        return {
            "success": True,
            "email": email,
            "deferral_count": deferral_count
        }
    
    except Exception as e:
        logger.error(f"Fear notification error: {e}")
        return {
            "error": str(e),
            "email": email
        }


async def send_fear_email(
    email: str,
    score: int,
    promo_code: str,
    scan_id: str
):
    """
    Send fear-based conversion email
    
    Subject: "Your ATS Score is X% — [UPGRADE to Pro & Fix It]"
    Body: Show score, top missing keywords, and 24h promo code
    """
    
    from backend.services.email_service import send_fear_email as _send_fear_email
    try:
        result = await _send_fear_email(
            db=None,
            user_id="free_scan",
            email=email,
            ats_score=float(score),
            full_name=email.split("@")[0],
        )
        if result:
            logger.info(f"Fear email sent to {email} with code {promo_code}")
        else:
            logger.warning(f"Fear email failed for {email} — check RESEND_API_KEY")
    except Exception as e:
        logger.error(f"Fear email error for {email}: {e}")


async def log_posthog_event(
    db: AsyncSession,
    event_type: str,
    email: str,
    metadata: dict = None
):
    """
    Log event to referral_events table (PostHog source)
    """
    try:
        stmt = text("""
            INSERT INTO referral_events (event_type, email, metadata)
            VALUES (:event_type, :email, CAST(:metadata AS jsonb))
        """)
        
        await db.execute(
            stmt,
            {
                "event_type": event_type,
                "email": email,
                "metadata": json.dumps(metadata or {})
            }
        )
        await db.commit()
    except Exception as e:
        logger.error(f"PostHog log error: {e}")

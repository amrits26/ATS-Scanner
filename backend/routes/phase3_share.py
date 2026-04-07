"""
Phase 3: Share & Referral Endpoints
POST /api/share/{scan_id} - Create shareable link
GET /share/{token} - Public share landing page
POST /api/webhook/resend-bounce - Email bounce handling
"""

from typing import Optional
import os
from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import stripe
from datetime import datetime

from backend.auth import verify_jwt_token  # Your JWT verification
from backend.database import get_db
from backend.services.referral_service import ReferralShareService, calculate_viral_coefficient
from backend.services.og_image_service import generate_og_image_job
from backend.utils.email_validator import validate_email
from backend.utils.idempotency import (
    record_share_request,
    check_share_rate_limit,
    generate_share_idempotency_key
)

router = APIRouter(prefix="/api", tags=["Phase 3"])

# ============================================================================
# Referral Service Initialization
# ============================================================================

STRIPE_API_KEY = os.getenv("STRIPE_API_KEY")
RESEND_API_KEY = os.getenv("RESEND_API_KEY")

referral_service = ReferralShareService(STRIPE_API_KEY)


# ============================================================================
# POST /api/share/{scan_id} - Create Share Link
# ============================================================================

@router.post("/share/{scan_id}")
async def create_share_link(
    scan_id: str,
    platform: str = "linkedin",  # linkedin, email, twitter
    jwt_token: str = Depends(verify_jwt_token),
    db: AsyncSession = Depends(get_db),
    background_tasks: BackgroundTasks = None
):
    """
    Create a shareable referral link with OG image and discount code
    
    Rate limited: 5 per minute per user
    
    Query params:
        platform: Share platform (linkedin, email, twitter)
    
    Returns:
        {
            "share_token": "...",
            "share_url": "https://intelliresume.ai/share/...",
            "discount_code": "REFER...",
            "og_image_url": "https://...",
            "valid_until": "2026-07-06T..."
        }
    """
    try:
        # Get user from JWT
        user_id = jwt_token.get("sub")
        user_email = jwt_token.get("email")
        user_name = jwt_token.get("name", "Friend")
        
        if not user_id:
            raise HTTPException(status_code=401, detail="Unauthorized")
        
        # Rate limit check (5 per minute)
        is_limited, remaining = await check_share_rate_limit(db, user_id, user_email)
        if is_limited:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limited. Try again in 60 seconds."
            )
        
        # Record share request for rate limiting
        await record_share_request(db, user_id, user_email)
        
        # Get analysis result
        stmt = text("""
            SELECT id, score, company_name, job_title, og_image_url
            FROM analysis_results
            WHERE id = :scan_id AND user_id = :user_id
            LIMIT 1
        """)
        
        result = await db.execute(stmt, {"scan_id": scan_id, "user_id": user_id})
        row = result.first()
        
        if not row:
            raise HTTPException(status_code=404, detail="Analysis not found")
        
        _, match_score, company_name, job_title, og_image_url = row
        
        # Create share (generates discount code, records in DB)
        share_result = await referral_service.create_share(
            db=db,
            scan_id=scan_id,
            user_id=user_id,
            user_email=user_email,
            user_name=user_name,
            match_score=match_score,
            company_name=company_name or "Dream Company",
            job_title=job_title or "Your Next Role",
            platform=platform
        )
        
        if not share_result.get("success"):
            raise HTTPException(
                status_code=400,
                detail=f"Share creation failed: {share_result.get('error')}"
            )
        
        # Enqueue OG image generation (background task)
        if background_tasks and not og_image_url:
            background_tasks.add_task(
                generate_og_image_job,
                db,
                scan_id=scan_id,
                match_score=match_score,
                company_name=company_name,
                job_title=job_title
            )
        
        return share_result
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# GET /share/{token} - Public Share Landing Page
# ============================================================================

@router.get("/share/{token}")
async def get_share(
    token: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Public landing page for shared analysis result
    
    Shows:
    - Match score
    - Company + Job title
    - OG image (LinkedIn preview)
    - Discount code (20% off)
    - Referrer name
    
    Returns:
        {
            "match_score": 82,
            "company_name": "Acme Inc",
            "job_title": "Senior Engineer",
            "og_image_url": "https://...",
            "discount_code": "REFERRAL20",
            "referrer_email": "user@example.com",
            "valid_until": "2026-07-06T..."
        }
    """
    try:
        share_details = await referral_service.get_share_by_token(db, token)
        
        if not share_details:
            raise HTTPException(status_code=404, detail="Share link not found or expired")
        
        return share_details
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# POST /api/referral/validate-code - Validate Discount Code
# ============================================================================

@router.post("/referral/validate-code")
async def validate_discount_code(
    discount_code: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Validate discount code before signup
    
    Called on checkout page to show discount amount
    
    Returns:
        {
            "valid": true,
            "discount_percent": 20,
            "valid_until": "2026-07-06T..."
        }
    """
    try:
        stmt = text("""
            SELECT discount_percent, valid_until
            FROM referral_discounts
            WHERE discount_code = :code
            AND valid_until > NOW()
            LIMIT 1
        """)
        
        result = await db.execute(stmt, {"code": discount_code.upper()})
        row = result.first()
        
        if not row:
            return {
                "valid": False,
                "error": "Invalid or expired discount code"
            }
        
        discount_percent, valid_until = row
        
        return {
            "valid": True,
            "discount_percent": discount_percent,
            "valid_until": valid_until.isoformat()
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# POST /api/webhook/resend-bounce - Resend Email Bounce Webhook
# ============================================================================

@router.post("/webhook/resend-bounce")
async def resend_bounce_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Handle Resend email bounce webhook
    
    Marks email as invalid/bounced to prevent future sends
    
    Expected payload:
        {
            "type": "email.bounced",
            "data": {
                "created_at": "2026-06-06T...",
                "email": "user@example.com",
                "bounce_type": "permanent",
                "bounce_reason": "smtp; 550 5.1.2 The email account that you tried to reach does not exist"
            }
        }
    """
    try:
        payload = await request.json()
        
        # Verify Resend signature (in production)
        # signature = request.headers.get("x-resend-signature")
        # if not verify_resend_signature(payload, signature, RESEND_API_KEY):
        #     raise HTTPException(status_code=401, detail="Invalid signature")
        
        event_type = payload.get("type")
        
        if event_type != "email.bounced":
            return {"received": True}  # Ignore other events
        
        data = payload.get("data", {})
        email = data.get("email", "").lower()
        bounce_type = data.get("bounce_type", "permanent")
        bounce_reason = data.get("bounce_reason", "")
        
        if not email:
            raise HTTPException(status_code=400, detail="Missing email")
        
        # Record bounce
        stmt = text("""
            INSERT INTO email_bounces (email, bounce_type, bounce_reason)
            VALUES (:email, :bounce_type, :bounce_reason)
            ON CONFLICT DO NOTHING
        """)
        
        await db.execute(
            stmt,
            {
                "email": email,
                "bounce_type": bounce_type,
                "bounce_reason": bounce_reason
            }
        )
        
        # If permanent bounce, flag user account
        if bounce_type == "permanent":
            stmt_flag = text("""
                UPDATE users
                SET email_verified = FALSE
                WHERE LOWER(email) = :email
            """)
            
            await db.execute(stmt_flag, {"email": email})
        
        await db.commit()
        
        return {"received": True, "processed": True}
    
    except Exception as e:
        print(f"Resend webhook error: {e}")
        return {"received": True, "processed": False}  # Return 200 to prevent retries


# ============================================================================
# GET /api/viral/coefficient - Get Viral Coefficient
# ============================================================================

@router.get("/viral/coefficient")
async def get_viral_coefficient(
    time_window_days: int = 30,
    db: AsyncSession = Depends(get_db)
):
    """
    Internal endpoint to monitor viral coefficient
    
    Returns:
        {
            "viral_coefficient": 0.82,
            "time_window_days": 30,
            "interpretation": "Sub-viral. Need > 1.0 for exponential growth"
        }
    """
    try:
        coefficient = await calculate_viral_coefficient(db, time_window_days)
        
        interpretation = (
            "Viral! Exponential growth" if coefficient > 1.0
            else "Sub-viral. Growing linearly" if coefficient > 0.5
            else "Cold start. Not viral yet"
        )
        
        return {
            "viral_coefficient": round(coefficient, 2),
            "time_window_days": time_window_days,
            "interpretation": interpretation
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Internal: Process Referral Conversion (called from signup)
# ============================================================================

async def process_referral_conversion(
    db: AsyncSession,
    share_token: Optional[str],
    referred_user_id: str,
    referred_email: str
):
    """
    Called when referred user successfully signs up for PRO
    Records viral conversion for coefficient tracking
    """
    if not share_token:
        return False
    
    try:
        # Get share ID from token
        stmt = text("""
            SELECT id FROM referral_shares
            WHERE share_token = :token
        """)
        
        result = await db.execute(stmt, {"token": share_token})
        row = result.first()
        
        if not row:
            return False
        
        share_id = row[0]
        
        # Record conversion
        conversion_result = await referral_service.record_referral_conversion(
            db,
            share_id=str(share_id),
            referred_user_id=referred_user_id,
            referred_email=referred_email
        )
        
        return conversion_result.get("success", False)
    
    except Exception as e:
        print(f"Error processing referral conversion: {e}")
        return False

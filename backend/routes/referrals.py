"""
Referral program routes for viral growth.

Endpoints:
  POST /api/referrals/generate-code - Generate user's referral code
  GET /api/referrals/stats - Get referral stats
  GET /api/referrals/{code} - Public referral landing page
  POST /api/referrals/redeem/{code} - Redeem referral code on signup
"""

import logging
import uuid
import random
import string
from datetime import datetime
from typing import Optional, Dict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..db_models import User, ReferralCode, ReferralConversion
from .auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/referrals", tags=["referrals"])

# ================================================================
# Pydantic Models
# ================================================================

class ReferralCodeResponse(BaseModel):
    """Referral code response"""
    code: str
    url: str
    created_at: datetime


class ReferralStatsResponse(BaseModel):
    """User's referral statistics"""
    code: str
    total_clicks: int
    total_signups: int
    active_referrals: int  # Currently on Pro/Premium
    total_commission: float  # Lifetime commission in dollars
    monthly_commission: Optional[float] = None  # This month only


class ReferralRedeemRequest(BaseModel):
    """Request to redeem referral code"""
    email: str
    referral_code: str


# ================================================================
# Helper Functions
# ================================================================

def generate_referral_code(length: int = 8) -> str:
    """Generate a unique referral code (e.g., PROMO2024ABC)"""
    chars = string.ascii_uppercase + string.digits
    return "PRO" + "".join(random.choices(chars, k=length))


# ================================================================
# Referral Routes
# ================================================================

@router.post("/generate-code", response_model=ReferralCodeResponse)
async def generate_referral_code_endpoint(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate (or retrieve existing) referral code for user.
    
    One code per user. If user already has a code, return existing one.
    """
    try:
        # Check if user already has a code
        stmt = select(ReferralCode).where(ReferralCode.user_id == current_user.id)
        result = await db.execute(stmt)
        referral_code = result.scalar_one_or_none()
        
        if referral_code:
            logger.info(f"[REFERRAL] Retrieved existing code for user {current_user.id}: {referral_code.code}")
            return ReferralCodeResponse(
                code=referral_code.code,
                url=f"https://yourapp.com/join?ref={referral_code.code}",
                created_at=referral_code.created_at
            )
        
        # Generate new code
        code = generate_referral_code()
        
        # Ensure uniqueness
        while (await db.execute(select(ReferralCode).where(ReferralCode.code == code))).scalar_one_or_none():
            code = generate_referral_code()
        
        # Create new referral code
        new_referral = ReferralCode(
            user_id=current_user.id,
            code=code,
            created_at=datetime.utcnow()
        )
        db.add(new_referral)
        await db.commit()
        
        logger.info(f"[REFERRAL] Generated new code for user {current_user.id}: {code}")
        
        return ReferralCodeResponse(
            code=code,
            url=f"https://yourapp.com/join?ref={code}",
            created_at=new_referral.created_at
        )
        
    except Exception as e:
        logger.error(f"[REFERRAL] Failed to generate code: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate referral code")


@router.get("/stats", response_model=ReferralStatsResponse)
async def get_referral_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get user's referral statistics and earnings"""
    try:
        # Get or create referral code
        stmt = select(ReferralCode).where(ReferralCode.user_id == current_user.id)
        result = await db.execute(stmt)
        referral_code = result.scalar_one_or_none()
        
        if not referral_code:
            # Return empty stats if no code yet
            return ReferralStatsResponse(
                code="",
                total_clicks=0,
                total_signups=0,
                active_referrals=0,
                total_commission=0.0,
                monthly_commission=0.0
            )
        
        # Get referral statistics
        stmt = select(ReferralConversion).where(ReferralConversion.referrer_id == current_user.id)
        result = await db.execute(stmt)
        referrals = result.scalars().all()
        
        # Count active referrals (still subscribed)
        active_referrals = sum(1 for r in referrals if r.status == "active")
        
        # Calculate commissions
        total_commission = sum(r.commission_amount for r in referrals)
        
        # Calculate this month's commission
        from datetime import datetime as dt
        now = dt.utcnow()
        current_month_referrals = [
            r for r in referrals
            if r.created_at.month == now.month and r.created_at.year == now.year
        ]
        monthly_commission = sum(r.commission_amount for r in current_month_referrals)
        
        logger.info(f"[REFERRAL] Stats for user {current_user.id}: {len(referrals)} referrals, ${total_commission:.2f} earned")
        
        return ReferralStatsResponse(
            code=referral_code.code,
            total_clicks=referral_code.clicks,
            total_signups=referral_code.signups,
            active_referrals=active_referrals,
            total_commission=total_commission,
            monthly_commission=monthly_commission
        )
        
    except Exception as e:
        logger.error(f"[REFERRAL] Failed to get stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve referral stats")


@router.get("/{code}", response_model=Dict)
async def get_referral_info(
    code: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Get public info about a referral code (for landing page).
    Does not return sensitive info, just verifies code exists.
    """
    try:
        stmt = select(ReferralCode).where(ReferralCode.code == code)
        result = await db.execute(stmt)
        referral_code = result.scalar_one_or_none()
        
        if not referral_code:
            raise HTTPException(status_code=404, detail="Referral code not found")
        
        # Increment click count
        referral_code.clicks += 1
        referral_code.last_used_at = datetime.utcnow()
        await db.commit()
        
        return {
            "code": code,
            "valid": True,
            "discount": "20% off Pro",
            "clicks": referral_code.clicks
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[REFERRAL] Failed to get referral info: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve referral info")


@router.post("/redeem/{code}")
async def redeem_referral_code(
    code: str,
    referred_user_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Redeem a referral code after new user signs up.
    
    Called by auth service after user creation.
    Creates ReferralConversion record and applies discount to their subscription.
    """
    try:
        # Get referral code
        stmt = select(ReferralCode).where(ReferralCode.code == code)
        result = await db.execute(stmt)
        referral_code = result.scalar_one_or_none()
        
        if not referral_code:
            logger.warning(f"[REFERRAL] Invalid code: {code}")
            return {"success": False, "detail": "Invalid referral code"}
        
        # Check if referred user already has a referral (prevent duplicates)
        stmt = select(ReferralConversion).where(
            ReferralConversion.referred_user_id == referred_user_id
        )
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()
        
        if existing:
            logger.warning(f"[REFERRAL] Referred user {referred_user_id} already has referral")
            return {"success": False, "detail": "User already referred"}
        
        # Get referred user
        stmt = select(User).where(User.id == referred_user_id)
        result = await db.execute(stmt)
        referred_user = result.scalar_one_or_none()
        
        if not referred_user:
            return {"success": False, "detail": "User not found"}
        
        # Create referral conversion record
        conversion = ReferralConversion(
            referrer_id=referral_code.user_id,
            referred_user_id=referred_user_id,
            referral_code_used=code,
            conversion_date=datetime.utcnow(),
            subscription_tier="free",  # Will be updated when they subscribe
            commission_rate=0.20,  # 20% default
            commission_amount=0.0,  # Will be updated on subscription
            status="pending"
        )
        db.add(conversion)
        
        # Update referral code signup count
        referral_code.signups += 1
        
        await db.commit()
        
        logger.info(f"[REFERRAL] Redeemed code {code} for user {referred_user_id} by referrer {referral_code.user_id}")
        
        return {"success": True, "discount_code": f"REFERRAL_{code}"}
        
    except Exception as e:
        logger.error(f"[REFERRAL] Failed to redeem code: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to redeem referral code")

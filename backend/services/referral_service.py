"""
Phase 3: Referral Share Service
Handles share creation, discount codes, viral tracking, and PostHog events
"""

from typing import Optional, Dict
from datetime import datetime, timedelta
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
import stripe
from backend.utils.idempotency import (
    generate_share_idempotency_key,
    record_share_request
)


class ReferralShareService:
    """
    Manages sharing, discount codes, and viral coefficient tracking
    """
    
    def __init__(self, stripe_api_key: str):
        stripe.api_key = stripe_api_key
    
    async def create_share(
        self,
        db: AsyncSession,
        scan_id: str,
        user_id: str,
        user_email: str,
        user_name: str,
        match_score: int,
        company_name: str,
        job_title: str,
        platform: str = "linkedin"
    ) -> Dict:
        """
        Create a shareable referral link with discount code
        
        Args:
            db: Database session
            scan_id: Analysis result ID
            user_id: User UUID
            user_email: User email
            user_name: User display name
            match_score: ATS score
            company_name: Company name
            job_title: Job title
            platform: Share platform (linkedin, email, twitter, etc.)
        
        Returns:
            Dict with share_token, share_url, discount_code, og_image_url
        """
        
        try:
            async with db.begin():
                # Generate share token
                share_token = generate_share_idempotency_key(user_id, scan_id)
                
                # Create referral share (atomic insert)
                stmt_share = text("""
                    INSERT INTO referral_shares 
                        (referrer_scan_id, referrer_user_id, referrer_email, share_token, platform)
                    VALUES (:scan_id, :user_id, :email, :token, :platform)
                    ON CONFLICT (share_token) DO NOTHING
                    RETURNING id
                """)
                
                result = await db.execute(
                    stmt_share,
                    {
                        "scan_id": scan_id,
                        "user_id": user_id,
                        "email": user_email,
                        "token": share_token,
                        "platform": platform
                    }
                )
                
                share_row = result.first()
                if not share_row:
                    # Token collision (extremely rare), retry
                    share_token = generate_share_idempotency_key(
                        user_id, scan_id, datetime.utcnow()
                    )
                    result = await db.execute(
                        stmt_share,
                        {
                            "scan_id": scan_id,
                            "user_id": user_id,
                            "email": user_email,
                            "token": share_token,
                            "platform": platform
                        }
                    )
                
                share_id = result.scalar()
                
                # Generate discount code (20% off)
                discount_code = self._generate_discount_code(user_name, scan_id)
                
                # Create Stripe coupon
                try:
                    stripe_coupon = stripe.Coupon.create(
                        percent_off=20,
                        duration="limited",
                        duration_in_months=3,  # Valid 3 months
                        id=discount_code  # Use code as coupon ID
                    )
                    stripe_coupon_id = stripe_coupon.id
                except stripe.error.InvalidRequestError:
                    # Coupon already exists
                    stripe_coupon_id = discount_code
                
                # Store discount code (atomic)
                valid_until = datetime.utcnow() + timedelta(days=90)
                
                stmt_discount = text("""
                    INSERT INTO referral_discounts 
                        (share_id, discount_code, stripe_coupon_id, discount_percent, valid_until)
                    VALUES (:share_id, :code, :coupon_id, 20, :valid_until)
                    ON CONFLICT (discount_code) DO NOTHING
                """)
                
                await db.execute(
                    stmt_discount,
                    {
                        "share_id": share_id,
                        "code": discount_code,
                        "coupon_id": stripe_coupon_id,
                        "valid_until": valid_until
                    }
                )
                
                # Update analysis_results with share metadata
                stmt_update_result = text("""
                    UPDATE analysis_results
                    SET share_token = :token, shared_at = NOW()
                    WHERE id = :scan_id
                """)
                
                await db.execute(
                    stmt_update_result,
                    {"token": share_token, "scan_id": scan_id}
                )
                
                # Enqueue OG image generation (ARQ job)
                # (In real implementation, this would be: arq.enqueue_job('generate_og_image_job', ...))
                
                # Log share event to PostHog
                await self._log_posthog_event(
                    db,
                    event_type="share_created",
                    user_id=user_id,
                    user_email=user_email,
                    share_id=share_id,
                    scan_id=scan_id,
                    metadata={
                        "platform": platform,
                        "match_score": match_score,
                        "discount_code": discount_code
                    }
                )
            
            return {
                "success": True,
                "share_token": share_token,
                "share_url": f"https://intelliresume.ai/share/{share_token}",
                "discount_code": discount_code,
                "discount_percent": 20,
                "valid_until": valid_until.isoformat()
            }
        
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    async def get_share_by_token(
        self,
        db: AsyncSession,
        share_token: str
    ) -> Optional[Dict]:
        """
        Retrieve share details by token (for public landing page)
        Also increments view count for viral tracking
        """
        try:
            async with db.begin():
                # Get share details with referrer info
                stmt = text("""
                    SELECT 
                        rs.id as share_id,
                        rs.referrer_user_id,
                        rs.referrer_email,
                        ar.score,
                        ar.company_name,
                        ar.job_title,
                        ar.og_image_url,
                        rd.discount_code,
                        rd.valid_until
                    FROM referral_shares rs
                    JOIN analysis_results ar ON rs.referrer_scan_id = ar.id
                    LEFT JOIN referral_discounts rd ON rs.id = rd.share_id
                    WHERE rs.share_token = :token
                """)
                
                result = await db.execute(stmt, {"token": share_token})
                row = result.first()
                
                if not row:
                    return None
                
                share_id = row[0]
                
                # Increment views
                stmt_view = text("""
                    UPDATE referral_shares
                    SET views_count = views_count + 1, last_view_at = NOW()
                    WHERE id = :share_id
                """)
                
                await db.execute(stmt_view, {"share_id": share_id})
                
                # Log view event
                await self._log_posthog_event(
                    db,
                    event_type="share_viewed",
                    share_id=share_id,
                    metadata={"views_total": row[6]}
                )
                
                return {
                    "share_id": str(share_id),
                    "referrer_email": row[2],
                    "match_score": row[3],
                    "company_name": row[4],
                    "job_title": row[5],
                    "og_image_url": row[6],
                    "discount_code": row[7],
                    "valid_until": row[8].isoformat() if row[8] else None
                }
        
        except Exception as e:
            print(f"Error retrieving share: {e}")
            return None
    
    async def record_referral_conversion(
        self,
        db: AsyncSession,
        share_id: str,
        referred_user_id: str,
        referred_email: str
    ) -> Dict:
        """
        Record when a referred user signs up and creates PRO account
        """
        try:
            async with db.begin():
                # Update referral_shares
                stmt = text("""
                    UPDATE referral_shares
                    SET referred_user_id = :ref_user_id, 
                        referred_email = :ref_email,
                        conversion_at = NOW()
                    WHERE id = :share_id
                """)
                
                await db.execute(
                    stmt,
                    {
                        "share_id": share_id,
                        "ref_user_id": referred_user_id,
                        "ref_email": referred_email
                    }
                )
                
                # Log conversion
                await self._log_posthog_event(
                    db,
                    event_type="share_converted",
                    share_id=share_id,
                    user_id=referred_user_id,
                    user_email=referred_email,
                    metadata={"referred_user_id": referred_user_id}
                )
                
                return {"success": True, "converted": True}
        
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def apply_referral_discount(
        self,
        db: AsyncSession,
        discount_code: str,
        user_email: str
    ) -> Dict:
        """
        Apply referral discount code to new customer
        Records the discount application for viral tracking
        """
        try:
            async with db.begin():
                # Get discount details
                stmt = text("""
                    SELECT rd.id, rd.stripe_coupon_id, rd.valid_until, rs.referrer_user_id
                    FROM referral_discounts rd
                    JOIN referral_shares rs ON rs.id = rd.share_id
                    WHERE rd.discount_code = :code
                    AND rd.valid_until > NOW()
                """)
                
                result = await db.execute(stmt, {"code": discount_code.upper()})
                row = result.first()
                
                if not row:
                    return {"success": False, "error": "Invalid or expired discount code"}
                
                discount_id, stripe_coupon_id, valid_until, referrer_user_id = row
                
                # Increment applied count
                stmt_increment = text("""
                    UPDATE referral_discounts
                    SET applied_count = applied_count + 1
                    WHERE discount_code = :code
                """)
                
                await db.execute(stmt_increment, {"code": discount_code.upper()})
                
                # Log discount application
                await self._log_posthog_event(
                    db,
                    event_type="discount_applied",
                    user_email=user_email,
                    metadata={
                        "discount_code": discount_code,
                        "referrer_user_id": str(referrer_user_id)
                    }
                )
                
                return {
                    "success": True,
                    "stripe_coupon_id": stripe_coupon_id,
                    "discount_percent": 20
                }
        
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _generate_discount_code(self, user_name: str, scan_id: str) -> str:
        """
        Generate unique discount code for referral
        Format: USER_{scan_id_short}
        """
        scan_short = scan_id[:8].upper()
        user_short = user_name.upper()[:4].replace(" ", "")
        code = f"REFER{user_short}{scan_short}"
        return code[:20]  # Stripe max 20 chars
    
    async def _log_posthog_event(
        self,
        db: AsyncSession,
        event_type: str,
        user_id: Optional[str] = None,
        user_email: Optional[str] = None,
        share_id: Optional[str] = None,
        scan_id: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> None:
        """
        Log referral event to PostHog tracking table
        (In real implementation, also send to PostHog API)
        """
        import json
        
        stmt = text("""
            INSERT INTO referral_events 
                (event_type, user_id, email, share_id, scan_id, metadata)
            VALUES (:event_type, :user_id, :email, :share_id, :scan_id, :metadata)
        """)
        
        await db.execute(
            stmt,
            {
                "event_type": event_type,
                "user_id": user_id,
                "email": user_email,
                "share_id": share_id,
                "scan_id": scan_id,
                "metadata": json.dumps(metadata or {})
            }
        )


# Viral coefficient calculation
async def calculate_viral_coefficient(
    db: AsyncSession,
    time_window_days: int = 30
) -> float:
    """
    Calculate viral coefficient = conversions / shares * 100
    
    k = (New users referred * Conversion Rate) / Original shares
    
    A k > 1 means viral growth
    """
    try:
        stmt = text("""
            WITH share_stats AS (
                SELECT 
                    COUNT(DISTINCT id) as total_shares,
                    COUNT(DISTINCT referred_user_id) FILTER (WHERE conversion_at IS NOT NULL) as conversions
                FROM referral_shares
                WHERE shared_at > NOW() - INTERVAL '{} days'
            )
            SELECT 
                CASE 
                    WHEN total_shares = 0 THEN 0.0
                    ELSE (conversions::float / total_shares::float)
                END as viral_coefficient
            FROM share_stats
        """.format(time_window_days))
        
        result = await db.execute(stmt)
        row = result.first()
        return row[0] if row else 0.0
    
    except Exception as e:
        print(f"Error calculating viral coefficient: {e}")
        return 0.0

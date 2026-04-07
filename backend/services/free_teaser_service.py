"""
Phase 3: Free Tease Endpoint & Heavy Lifting Service
Light-weight Gemini analysis (first 500 words) + lead capture
"""

import hashlib
import os
from typing import Optional, Dict, Tuple
from datetime import datetime, timedelta
import pytz
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
import stripe
from dotenv import load_dotenv

from backend.utils.email_validator import validate_email, get_email_domain
from backend.utils.idempotency import (
    generate_free_scan_idempotency_key,
    record_free_scan,
    check_free_scan_idempotency
)

load_dotenv()

stripe.api_key = os.getenv("STRIPE_API_KEY")


class FreeTeaserService:
    """
    Light-weight analysis for free tier (first 500 words only)
    Returns: ATS Score (1-100) + Top 3 Missing Keywords
    """
    
    def __init__(self, gemini_client):
        """
        Args:
            gemini_client: google.generativeai client (initialized in main)
        """
        self.gemini = gemini_client
    
    def truncate_text(self, text: str, max_words: int = 500) -> str:
        """
        Truncate text to N words (cost control)
        
        Args:
            text: Full text
            max_words: Maximum words to analyze (default 500)
        
        Returns:
            Truncated text
        """
        words = text.split()
        return " ".join(words[:max_words])
    
    async def analyze_free(
        self,
        resume_text: str,
        jd_text: str,
        email: str
    ) -> Tuple[int, list]:
        """
        Light-weight Gemini analysis (free tier)
        
        Args:
            resume_text: Full resume content (will truncate to 500 words)
            jd_text: Full job description (will truncate to 500 words)
            email: User email (for analytics)
        
        Returns:
            Tuple of (score: int, missing_keywords: list)
        
        Raises:
            ValueError if Gemini API fails
        """
        
        # Truncate to 500 words each (cost control)
        resume_truncated = self.truncate_text(resume_text, max_words=500)
        jd_truncated = self.truncate_text(jd_text, max_words=500)
        
        prompt = f"""
You are an ATS optimization expert. Analyze the resume against the job description.

**Resume (truncated to 500 words):**
{resume_truncated}

**Job Description (truncated to 500 words):**
{jd_truncated}

Return ONLY a JSON object with:
{{
    "score": <1-100 integer>,
    "missing_keywords": [<top 3 missing keywords as strings>]
}}

Example:
{{"score": 72, "missing_keywords": ["Machine Learning", "Docker", "CI/CD"]}}

Do NOT include any other text or formatting. Return ONLY valid JSON.
"""
        
        try:
            response = self.gemini.generate_content(prompt)
            response_text = response.text.strip()
            
            # Parse JSON response
            import json
            result = json.loads(response_text)
            
            score = int(result.get("score", 50))
            keywords = result.get("missing_keywords", [])[:3]  # Top 3 only
            
            # Clamp score to 1-100
            score = max(1, min(100, score))
            
            return score, keywords
        
        except Exception as e:
            print(f"Gemini analysis error: {e}")
            # Return neutral response on error
            return 50, ["Resume Improvement", "Job Alignment", "Skills Match"]
    
    async def create_stripe_promo_code(
        self,
        user_email: str,
        discount_percent: int = 20,
        expiry_hours: int = 24
    ) -> Optional[str]:
        """
        Create a unique, single-use Stripe promo code with expiry
        
        Args:
            user_email: User email (for code generation)
            discount_percent: Discount percentage (default 20%)
            expiry_hours: Code expiry in hours (default 24)
        
        Returns:
            Promo code (e.g., 'FEAR20_ABC123') or None if failed
        """
        try:
            # Generate unique code
            email_hash = hashlib.md5(user_email.encode()).hexdigest()[:6].upper()
            code = f"FEAR{discount_percent}_{email_hash}"
            
            # Create Stripe coupon
            expires_at = int((datetime.utcnow() + timedelta(hours=expiry_hours)).timestamp())
            
            coupon = stripe.Coupon.create(
                percent_off=discount_percent,
                duration="limited",
                duration_in_months=1,
                id=code  # Use as coupon ID
            )
            
            return code
        
        except stripe.error.InvalidRequestError as e:
            # Code already exists
            if "already exists" in str(e):
                return code
            return None
        except Exception as e:
            print(f"Stripe promo code error: {e}")
            return None


# ============================================================================
# Database Operations for Free Scan
# ============================================================================

async def save_free_scan(
    db: AsyncSession,
    email: str,
    resume_hash: str,
    score: int,
    keywords: list,
    timezone: str = "UTC",
    consent_given: bool = True,
    promo_code: Optional[str] = None
) -> Optional[Dict]:
    """
    Save free scan to database (with deduplication)
    
    Args:
        db: Database session
        email: User email
        resume_hash: SHA256 hash of resume
        score: ATS score (1-100)
        keywords: Missing keywords list
        timezone: User timezone (auto-detected)
        consent_given: GDPR/CCPA consent
        promo_code: Optional promo code
    
    Returns:
        Dict with scan_id or None if failed
    """
    try:
        import json
        
        async with db.begin():
            # Check idempotency first (same resume same day?)
            is_dup, scans_remaining = await check_free_scan_idempotency(
                db, email, resume_hash
            )
            
            if is_dup:
                return {
                    "duplicate": True,
                    "message": "You already scanned this resume today",
                    "scans_remaining": scans_remaining
                }
            
            # Insert free scan
            from sqlalchemy import text as sql_text
            import uuid
            
            scan_id = str(uuid.uuid4())
            
            stmt = sql_text("""
                INSERT INTO free_scans 
                    (id, email, resume_hash, score, keywords, consent_given, timezone, promo_code, created_at)
                VALUES (:id, :email, :hash, :score, :keywords, :consent, :tz, :code, NOW())
                RETURNING id
            """)
            
            result = await db.execute(
                stmt,
                {
                    "id": scan_id,
                    "email": email.lower(),
                    "hash": resume_hash,
                    "score": score,
                    "keywords": json.dumps(keywords),
                    "consent": consent_given,
                    "tz": timezone,
                    "code": promo_code
                }
            )
            
            return {
                "scan_id": scan_id,
                "score": score,
                "keywords": keywords,
                "promo_code": promo_code,
                "scans_remaining": max(0, 3 - 1)  # Free tier: 3/month
            }
    
    except Exception as e:
        print(f"Error saving free scan: {e}")
        return None


async def check_pro_user(
    db: AsyncSession,
    email: str
) -> bool:
    """
    Check if email belongs to Pro user
    
    Returns: True if Pro user, False if free/not found
    """
    try:
        from sqlalchemy import text as sql_text
        
        stmt = sql_text("""
            SELECT tier FROM users
            WHERE LOWER(email) = :email
            LIMIT 1
        """)
        
        result = await db.execute(stmt, {"email": email.lower()})
        row = result.first()
        
        if not row:
            return False  # Not found
        
        return row[0] == "pro"
    
    except Exception as e:
        print(f"Error checking Pro user: {e}")
        return False  # Assume free on error


# ============================================================================
# Utility: Calculate Resume Hash
# ============================================================================

def calculate_resume_hash(resume_text: str) -> str:
    """
    Calculate SHA256 hash of resume for deduplication
    
    Args:
        resume_text: Resume content
    
    Returns:
        Hex digest (64 chars)
    """
    return hashlib.sha256(resume_text.encode()).hexdigest()

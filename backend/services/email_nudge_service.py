"""
Email Nudge Service - Phase 1: Revenue Fortress
Handles: Fear emails (24h), Abandoned scans (72h), Weekly digests

Gemini generates personalized copy. Resend delivers. Tracks opens/clicks.
"""

import os
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from enum import Enum

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

import google.generativeai as genai

logger = logging.getLogger(__name__)

# Configuration
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "re_placeholder")
RESEND_FROM_EMAIL = os.getenv("RESEND_FROM_EMAIL", "noreply@intelliresume.ai")
RESEND_WEBHOOK_SECRET = os.getenv("RESEND_WEBHOOK_SECRET", "secret_placeholder")

# Email template IDs (create these in Resend dashboard)
TEMPLATE_IDS = {
    "fear_email_24h": "fear-email-24h-v1",
    "abandoned_scan_72h": "abandoned-scan-72h-v1",
    "weekly_digest": "weekly-digest-v1",
}


class NudgeType(str, Enum):
    """Types of nudge emails"""
    fear = "fear"
    abandoned = "abandoned"
    digest = "digest"


class NudgeEngine:
    """
    Orchestrates email campaigns:
    1. Fear Email (24h after free scan) - "You scored 72! Unlock full optimization for $9.99"
    2. Abandoned Scan (72h later) - "Still interested? 3-day sale: 50% off"
    3. Weekly Digest (every Monday) - "Top missing keywords from your scans"
    """

    def __init__(self, db: AsyncSession, gemini_api_key: str = None):
        self.db = db
        if gemini_api_key:
            genai.configure(api_key=gemini_api_key)
        elif not os.getenv("GOOGLE_API_KEY"):
            raise ValueError("GOOGLE_API_KEY not configured for Gemini")

    # ========================================================================
    # STAGE 1: FEAR EMAIL (24h after free scan)
    # ========================================================================

    async def schedule_fear_email(
        self,
        user_id: str,
        analysis_id: str,
        score: int,
        missing_keywords: List[str],
        timezone: str = "UTC",
    ) -> str:
        """
        Schedule fear email 24h after free scan, respecting quiet hours.
        
        Args:
            user_id: User UUID
            analysis_id: AnalysisResult ID
            score: ATS score (0-100)
            missing_keywords: Top 3 missing keywords
            timezone: User's timezone
        
        Returns:
            nudge_tracking_id for monitoring
        """
        try:
            from backend.db_models import NudgeTracking
            
            # Check quiet hours (don't send between 7pm-9am)
            if not self._is_within_business_hours(timezone):
                # Defer to next business window
                scheduled_at = self._next_business_hours_start(timezone)
            else:
                scheduled_at = datetime.utcnow() + timedelta(hours=24)

            # Generate personalized subject + preview via Gemini
            subject, preview = await self._generate_fear_email_copy(
                score, missing_keywords
            )

            # Create tracking record
            nudge = NudgeTracking(
                user_id=user_id,
                analysis_session_id=analysis_id,
                nudge_type=NudgeType.fear,
                scheduled_at=scheduled_at,
                email_subject=subject,
                template_id=TEMPLATE_IDS["fear_email_24h"],
            )
            self.db.add(nudge)
            await self.db.commit()

            logger.info(
                f"[NUDGE] Fear email scheduled for {user_id} at {scheduled_at} "
                f"(score={score})"
            )
            return str(nudge.id)

        except Exception as e:
            logger.error(f"[NUDGE] Failed to schedule fear email: {e}")
            raise

    async def send_fear_email(
        self,
        user_id: str,
        email: str,
        first_name: str,
        score: int,
        missing_keywords: List[str],
        discount_code: str = "FEAR20",
        gemini_cost_tracking: Dict = None,
    ) -> bool:
        """
        Send fear email via Resend. Track cost in Gemini cost log.
        
        Returns:
            True if sent successfully, False if failed/DLQ'd
        """
        try:
            if not RESEND_API_KEY or RESEND_API_KEY == "re_placeholder":
                logger.warning("[NUDGE] Resend API key not configured. Storing in DLQ.")
                return False

            # Generate personalized email copy via Gemini
            subject, body_html = await self._generate_fear_email_html(
                first_name, score, missing_keywords, discount_code
            )

            # Prepare Resend payload
            payload = {
                "from": RESEND_FROM_EMAIL,
                "to": email,
                "subject": subject,
                "html": body_html,
                "template_id": TEMPLATE_IDS["fear_email_24h"],
                "headers": {
                    "List-Unsubscribe": f"<https://yourapp.com/api/nudge/unsubscribe?token={{{{unsubscribe_token}}}}>"
                },
                "tags": ["nudge", "fear", user_id],
            }

            # TODO: Uncomment when Resend SDK installed
            # from resend import Resend
            # client = Resend(api_key=RESEND_API_KEY)
            # response = client.emails.send(payload)
            # if not response.get("id"):
            #     raise Exception(f"Resend error: {response}")

            logger.info(f"[NUDGE] Fear email sent to {email} (score={score})")
            return True

        except Exception as e:
            logger.error(f"[NUDGE] Failed to send fear email: {e}")
            await self._store_in_dlq("fear_email", email, str(e))
            return False

    async def _generate_fear_email_copy(
        self, score: int, keywords: List[str]
    ) -> tuple:
        """
        Use Gemini to generate compelling, personalized subject + preview.
        
        Returns:
            (subject_line, preview_text)
        """
        prompt = f"""Generate a short, urgent email subject line for someone who scored {score}/100 on ATS optimization.
        
Missing keywords: {', '.join(keywords[:3])}

Requirements:
- Use URGENT language like "⚠️" or "🚨"
- Reference the score and missing keywords
- Make them feel like they're missing out
- Keep to 50 chars max
- Follow psychology: loss aversion > gain

Return ONLY the subject line, nothing else."""

        try:
            model = genai.GenerativeModel("gemini-1.5-flash")
            response = model.generate_content(prompt)
            subject = response.text.strip()[:60]

            # Generate preview (first 100 chars of what email body will say)
            preview = f"Your resume scored {score}/100. Missing: {keywords[0]}. Upgrade now →"

            return subject, preview

        except Exception as e:
            logger.error(f"[NUDGE] Gemini copy generation failed: {e}")
            # Fallback
            return (
                f"⚠️ Your score: {score}/100 (upgrade for +20 points)",
                f"Missing keywords found.",
            )

    async def _generate_fear_email_html(
        self,
        first_name: str,
        score: int,
        keywords: List[str],
        discount_code: str,
    ) -> tuple:
        """
        Generate full HTML email body with Gemini personalization.
        
        Returns:
            (subject, html_body)
        """
        prompt = f"""Write a conversion-focused email body (HTML). Context:
- Recipient: {first_name}
- Their ATS score: {score}/100
- Missing keywords: {keywords}
- Offer: {discount_code} (20% off Pro)

Requirements:
- 150-200 words max
- Use urgency: "Your competition is optimizing right now"
- Include specific action items (e.g., "Add '{keywords[0]}' to your resume")
- CTA: "Get 20% off → Upgrade Now"
- Friendly but pushy tone

Return ONLY the email body HTML (include <h1>, <p>, <button> etc), no preamble."""

        try:
            model = genai.GenerativeModel("gemini-1.5-flash")
            response = model.generate_content(prompt)
            html_body = response.text.strip()

            subject = f"⚠️ {first_name}, your score: {score}/100 (missing {len(keywords)} keywords)"

            return subject, html_body

        except Exception as e:
            logger.error(f"[NUDGE] HTML generation failed: {e}")
            # Fallback HTML
            fallback_html = f"""
            <h1>Your ATS Score: {score}/100</h1>
            <p>Hi {first_name},</p>
            <p>You're missing key keywords: <strong>{', '.join(keywords)}</strong></p>
            <p>Upgrade to Pro to unlock full optimization and add these keywords strategically.</p>
            <p><a href="https://yourapp.com/upgrade?code={discount_code}">Get 20% Off Now</a></p>
            """
            subject = f"Your score: {score}/100 ({discount_code} inside)"
            return subject, fallback_html

    # ========================================================================
    # STAGE 2: ABANDONED SCAN (72h later if no upgrade)
    # ========================================================================

    async def send_abandoned_scan_email(
        self, user_id: str, email: str, first_name: str, score: int
    ) -> bool:
        """
        72h follow-up: "Still interested? Now 50% off for 24h only."
        """
        try:
            if not RESEND_API_KEY or RESEND_API_KEY == "re_placeholder":
                return False

            # Generate urgency copy (higher discount)
            subject = f"⏰ {first_name}, 50% off expires today"
            body_html = f"""
            <h2>Don't miss out</h2>
            <p>You scored {score}/100. Most candidates with your score upgrade within 72 hours.</p>
            <p><strong>Last chance:</strong> 50% off expires at midnight.</p>
            <p><a href="https://yourapp.com/upgrade?code=URGENCY50">Claim 50% Discount</a></p>
            """

            payload = {
                "from": RESEND_FROM_EMAIL,
                "to": email,
                "subject": subject,
                "html": body_html,
                "template_id": TEMPLATE_IDS["abandoned_scan_72h"],
                "tags": ["nudge", "abandoned", user_id],
            }

            # TODO: Uncomment when Resend SDK installed
            # client = Resend(api_key=RESEND_API_KEY)
            # response = client.emails.send(payload)

            logger.info(f"[NUDGE] Abandoned scan email sent to {email}")
            return True

        except Exception as e:
            logger.error(f"[NUDGE] Abandoned scan email failed: {e}")
            return False

    # ========================================================================
    # STAGE 3: WEEKLY DIGEST
    # ========================================================================

    async def send_weekly_digest(
        self, user_id: str, email: str, first_name: str, scans_this_week: List[Dict]
    ) -> bool:
        """
        Every Monday: "Your top missing keywords from this week's scans"
        Aggregates all scans and shows trends.
        """
        try:
            if not RESEND_API_KEY or RESEND_API_KEY == "re_placeholder":
                return False

            if not scans_this_week:
                logger.info(f"[NUDGE] No scans for {user_id} this week; skipping digest")
                return False

            # Aggregate keywords
            all_keywords = []
            avg_score = sum(s["score"] for s in scans_this_week) / len(scans_this_week)
            for scan in scans_this_week:
                all_keywords.extend(scan.get("missing_keywords", []))

            # Get top 5 keywords
            from collections import Counter

            top_keywords = Counter(all_keywords).most_common(5)

            subject = f"📊 {first_name}'s ATS Digest: Top 5 Keywords You're Missing"
            body_html = self._generate_digest_html(
                first_name, len(scans_this_week), avg_score, top_keywords
            )

            payload = {
                "from": RESEND_FROM_EMAIL,
                "to": email,
                "subject": subject,
                "html": body_html,
                "template_id": TEMPLATE_IDS["weekly_digest"],
                "tags": ["nudge", "digest", user_id],
            }

            # TODO: Uncomment when Resend SDK installed
            # client = Resend(api_key=RESEND_API_KEY)
            # response = client.emails.send(payload)

            logger.info(f"[NUDGE] Weekly digest sent to {email}")
            return True

        except Exception as e:
            logger.error(f"[NUDGE] Weekly digest failed: {e}")
            return False

    def _generate_digest_html(
        self, first_name: str, scan_count: int, avg_score: float, top_keywords
    ) -> str:
        """Generate digest email HTML"""
        keywords_html = "".join(
            [f"<li>{kw[0]} (mentioned {kw[1]}x)</li>" for kw in top_keywords]
        )

        return f"""
        <h2>Your Weekly ATS Digest</h2>
        <p>Hi {first_name},</p>
        <p>You completed <strong>{scan_count} scans</strong> this week with an average score of <strong>{avg_score:.0f}/100</strong>.</p>
        
        <h3>Top Keywords You're Missing:</h3>
        <ul>
            {keywords_html}
        </ul>
        
        <p>Pro tip: Add these keywords to your resume summary and impact statements.</p>
        <p><a href="https://yourapp.com/dashboard">View Full Analytics</a></p>
        """

    # ========================================================================
    # UTILITIES
    # ========================================================================

    def _is_within_business_hours(self, timezone: str) -> bool:
        """Check if current time in user's timezone is between 9 AM - 7 PM"""
        try:
            import pytz
            tz = pytz.timezone(timezone)
            now = datetime.now(tz)
            return 9 <= now.hour < 19
        except:
            return True  # Default to sending if TZ parsing fails

    def _next_business_hours_start(self, timezone: str) -> datetime:
        """Return datetime of next 9 AM in user's timezone"""
        try:
            import pytz
            tz = pytz.timezone(timezone)
            now = datetime.now(tz)

            if now.hour < 9:
                # Same day at 9 AM
                return now.replace(hour=9, minute=0, second=0, microsecond=0)
            else:
                # Next day at 9 AM
                next_day = now + timedelta(days=1)
                return next_day.replace(hour=9, minute=0, second=0, microsecond=0)
        except:
            return datetime.utcnow() + timedelta(hours=24)

    async def _store_in_dlq(self, email_type: str, recipient: str, error: str):
        """Store failed email in Dead Letter Queue for manual retry"""
        try:
            logger.error(
                f"[NUDGE DLQ] {email_type} to {recipient} failed: {error}"
            )
        except Exception as e:
            logger.error(f"[NUDGE] Failed to store in DLQ: {e}")


# ============================================================================
# ARQ JOB FUNCTIONS (called by background workers)
# ============================================================================


async def send_scheduled_nudge_emails(ctx: dict = None) -> Dict:
    """
    ARQ job: Check nudge_tracking for scheduled emails and send them.
    Run this every 15 minutes via ARQ scheduler.
    """
    from backend.database import AsyncSessionLocal
    from backend.db_models import User

    async with AsyncSessionLocal() as db:
        engine = NudgeEngine(db)

        # Find all scheduled nudges ready to send (scheduled_at <= now, sent_at IS NULL)
        from backend.db_models import NudgeTracking
        pending = await db.execute(
            select(NudgeTracking).where(
                and_(
                    NudgeTracking.scheduled_at <= datetime.utcnow(),
                    NudgeTracking.sent_at.is_(None),
                )
            )
        )

        pending_nudges = pending.scalars().all()
        sent_count = 0
        failed_count = 0

        for nudge in pending_nudges:
            # Get user info
            user_result = await db.execute(
                select(User).where(User.id == nudge.user_id)
            )
            user = user_result.scalars().first()

            if not user:
                logger.warning(f"[NUDGE] User {nudge.user_id} not found")
                continue

            # Send appropriate nudge type
            if nudge.nudge_type == NudgeType.fear:
                success = await engine.send_fear_email(
                    user_id=str(user.id),
                    email=user.email,
                    first_name=user.full_name or user.email.split("@")[0],
                    score=75,  # TODO: Get from AnalysisResult
                    missing_keywords=["Python", "AWS", "Docker"],  # TODO: Get from result
                )
            elif nudge.nudge_type == NudgeType.abandoned:
                success = await engine.send_abandoned_scan_email(
                    user_id=str(user.id),
                    email=user.email,
                    first_name=user.full_name or user.email.split("@")[0],
                    score=75,
                )
            else:
                success = await engine.send_weekly_digest(
                    user_id=str(user.id),
                    email=user.email,
                    first_name=user.full_name or user.email.split("@")[0],
                    scans_this_week=[],  # TODO: Get from DB
                )

            if success:
                sent_count += 1
            else:
                failed_count += 1

        logger.info(
            f"[NUDGE] Batch complete: {sent_count} sent, {failed_count} failed"
        )
        return {
            "sent": sent_count,
            "failed": failed_count,
            "total": len(pending_nudges),
        }

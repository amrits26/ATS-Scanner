"""
SQLAlchemy ORM models for IntelliResume AI.

Tables:
  users            — registered users, tier, Stripe subscription info
  analysis_results — per-scan results with async status + result JSON cache
"""

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from .database import Base


# ---------------------------------------------------------------------------
# Enums (Python-side; mirrored in SQL via migrations/001_init.sql)
# ---------------------------------------------------------------------------

class UserTier(str, enum.Enum):
    free = "free"
    pro = "pro"
    agency = "agency"  # NEW: 3-tier pricing support


class SubscriptionStatus(str, enum.Enum):
    active = "active"
    trialing = "trialing"
    canceled = "canceled"
    past_due = "past_due"
    unpaid = "unpaid"


class AnalysisStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------

class User(Base):
    """
    Application user, linked to Supabase Auth via supabase_user_id.

    Tier logic:
      free  — max 3 scans/month; receives ATS score + top 3 missing keywords only
      pro   — unlimited scans; full result including OptimizedResume + SkillGap + DOCX
    """
    __tablename__ = "users"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    # Supabase auth.users.id — used to look up the user after JWT verification
    supabase_user_id = Column(String(255), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False)
    full_name = Column(String(255), nullable=True)

    # Subscription
    tier = Column(
        Enum(UserTier, name="user_tier"),
        nullable=False,
        default=UserTier.free,
    )
    stripe_customer_id = Column(String(255), nullable=True)
    stripe_subscription_id = Column(String(255), nullable=True)
    subscription_status = Column(
        Enum(SubscriptionStatus, name="subscription_status"),
        nullable=True,
    )

    # Rate limiting
    scans_this_month = Column(Integer, nullable=False, default=0)
    scan_limit = Column(Integer, nullable=False, default=3)  # -1 = unlimited
    scan_reset_date = Column(Date, nullable=True)            # reset on this date
    monthly_scan_limit = Column(Integer, nullable=False, default=3)  # NEW: For 3-tier pricing
    health_email_opt_in = Column(Boolean, nullable=False, default=False)  # NEW: Email preferences
    plan_type = Column(String(50), nullable=False, default="monthly")  # NEW: onetime, monthly, annual

    # Phase 2: Timezone-aware retention + upgrade tracking
    timezone = Column(String(50), nullable=False, default="UTC")
    last_fear_email_sent_at = Column(DateTime(timezone=True), nullable=True)
    upgrade_source = Column(String(100), nullable=True)  # 'web', 'email_campaign', etc.

    # Timestamps (updated_at is maintained by DB trigger in 001_init.sql)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    analyses = relationship(
        "AnalysisResult",
        back_populates="user",
        lazy="select",
        order_by="AnalysisResult.created_at.desc()",
    )

    def can_scan(self) -> bool:
        """Returns True if the user has scans remaining this month."""
        if self.tier == UserTier.pro:
            return True
        if self.tier == UserTier.agency:
            # Agency: 50 scans/month limit
            return self.scans_this_month < 50
        if self.scan_limit == -1:
            return True
        return self.scans_this_month < self.scan_limit


# ---------------------------------------------------------------------------
# AnalysisResult
# ---------------------------------------------------------------------------

class AnalysisResult(Base):
    """
    One per user scan.  Status transitions:
      pending → processing → completed
                           ↘ failed

    result_json stores the full ComprehensiveAnalysisResult payload so the
    frontend can poll /api/analysis/{session_id}/status until completed,
    then fetch the cached JSON — avoiding a second LLM call.

    Cache: if (resume_text_hash, jd_text_hash) matches a 'completed' row
    created within 24 hours, the backend returns that result_json directly.
    """
    __tablename__ = "analysis_results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Public-facing polling key
    session_id = Column(String(255), unique=True, nullable=False, index=True)

    status = Column(
        Enum(AnalysisStatus, name="analysis_status"),
        nullable=False,
        default=AnalysisStatus.pending,
    )

    resume_filename = Column(String(500), nullable=True)

    # SHA-256 hashes of raw inputs — used for 24-hour result caching
    resume_text_hash = Column(String(64), nullable=True, index=True)
    jd_text_hash = Column(String(64), nullable=True, index=True)

    # --- Step-level progress tracking (Phase 1: The Engine) ---
    current_step = Column(Integer, nullable=False, default=0)  # 0-10 (0=pending, 1-8=steps, 9-10=post-processing)
    step_message = Column(String(255), nullable=True)  # e.g., "Analyzing Job Description..."
    progress_percent = Column(Integer, nullable=False, default=0)  # 0-100
    step_timestamps = Column(JSONB, nullable=True)  # {step_1: timestamp, step_2: ...}
    retry_count = Column(Integer, nullable=False, default=0)  # How many retries for this job

    # Phase 2: Retention loop (fear notifications) + deferral guards
    fear_email_sent = Column(Boolean, nullable=False, default=False)  # Boolean flag (Ironclad Fix #3)
    last_fear_email_at = Column(DateTime(timezone=True), nullable=True)  # Last sent timestamp
    fear_deferral_count = Column(Integer, nullable=False, default=0)  # Track <= 5 deferrals (guard)

    # Full serialized ComprehensiveAnalysisResult (gated fields stripped for free tier)
    result_json = Column(JSONB, nullable=True)

    # Phase 1 & 3: Real-Time Intelligence
    live_keywords_metadata = Column(JSONB, nullable=True, default={})  # Live keyword feed during optimization

    error_message = Column(Text, nullable=True)

    # Phase 1: AI Quality Feedback (user thumbs up/down) [GAP 3 FIX: Boolean type]
    user_feedback = Column(Boolean, nullable=True)  # True=helpful, False=not helpful (NOT Integer)
    feedback_reason = Column(String(100), nullable=True)  # "too_low", "too_high", "keywords_wrong", etc.
    feedback_notes = Column(Text, nullable=True)  # Free text feedback
    feedback_at = Column(DateTime(timezone=True), nullable=True)  # When feedback submitted

    # Phase 3: Referral tracking
    og_image_url = Column(Text, nullable=True)  # LinkedIn OG image URL
    og_image_ready = Column(Boolean, nullable=False, default=False)  # True = image generated & ready for share
    shared_at = Column(DateTime(timezone=True), nullable=True)  # When shared
    share_token = Column(String(255), nullable=True, unique=True, index=True)  # Public share link

    # User's timezone for quiet hours enforcement
    user_timezone = Column(String(50), nullable=False, default="UTC")  # e.g., "America/New_York"

    # Phase 6: Credibility Layer (user confidence + transparency)
    percentile_rank = Column(Integer, nullable=True, default=None)  # 0-100, where user ranks (higher = better)
    confidence_score = Column(Integer, nullable=True, default=None)  # 0-100, confidence in score accuracy
    algorithm_breakdown = Column(JSONB, nullable=True)  # {"keywords": 40, "format": 30, "experience": 20, "structure": 10}
    keyword_impact_data = Column(JSONB, nullable=True)  # [{"keyword": "Python", "impact_percent": 1.8, "confidence": 0.85}, ...]

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    user = relationship("User", back_populates="analyses")


# ---------------------------------------------------------------------------
# Phase 3: The Feedback Loop — Model Training
# ---------------------------------------------------------------------------

class AnalysisFeedback(Base):
    """
    Phase 3: User feedback on analysis accuracy
    Used to aggregate patterns and improve AI model prompts
    """
    __tablename__ = "analysis_feedback"

    id = Column(Integer, primary_key=True)
    analysis_id = Column(
        UUID(as_uuid=True),
        ForeignKey("analysis_results.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Accuracy rating 1-5: How accurate was the ATS score?
    score_accuracy = Column(Integer, nullable=False)  # CHECK: 1-5
    
    # Was this feedback helpful?
    was_helpful = Column(Boolean, nullable=False)
    
    # Free-text feedback
    user_notes = Column(Text, nullable=True)
    
    # Timestamp
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )

    # Relationship back to analysis
    analysis = relationship("AnalysisResult", foreign_keys=[analysis_id])


# ---------------------------------------------------------------------------
# Phase 3: Viral Loop Models
# ---------------------------------------------------------------------------

class FreeScan(Base):
    """
    Free tier lightweight scan (first 500 words)
    Captures lead with email + score + minimal keywords
    Idempotency: unique constraint on (email, resume_hash, scan_date)
    """
    __tablename__ = "free_scans"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), nullable=False, index=True)
    resume_hash = Column(String(64), nullable=False)  # SHA256
    
    # Score + minimal analysis
    score = Column(Integer, nullable=False)  # 1-100
    keywords = Column(JSONB, nullable=False, default=[])  # Top 3 missing keywords
    
    # Consent + metadata
    consent_given = Column(Boolean, nullable=False, default=False)  # Boolean (Ironclad Fix #3)
    timezone = Column(String(50), nullable=False, default="UTC")
    
    # Fear loop tracking
    fear_email_sent = Column(Boolean, nullable=False, default=False)  # Boolean (Ironclad Fix #3)
    fear_email_sent_at = Column(DateTime(timezone=True), nullable=True)
    
    # Viral tracking
    referrer_scan_id = Column(UUID(as_uuid=True), nullable=True)  # For attribution
    
    # Conversion
    promo_code = Column(String(50), nullable=True)
    
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class FreeScanUsage(Base):
    """
    Track free tier scan usage (3 scans per month)
    Idempotency: unique constraint on (email, resume_hash, scan_date)
    """
    __tablename__ = "free_scan_usage"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    email = Column(String(255), nullable=False, index=True)
    resume_hash = Column(String(64), nullable=False)  # SHA256
    scan_date = Column(Date, nullable=False, default=date.today, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class ReferralShare(Base):
    """
    Shareable referral link with viral tracking
    Links referrer's scan to potential referred users
    """
    __tablename__ = "referral_shares"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    referrer_scan_id = Column(
        UUID(as_uuid=True),
        ForeignKey("analysis_results.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    referrer_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    referrer_email = Column(String(255), nullable=False)

    share_token = Column(String(255), unique=True, nullable=False, index=True)
    platform = Column(String(50), nullable=False, default="linkedin")
    shared_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    # Viral tracking
    views_count = Column(Integer, nullable=False, default=0)
    last_view_at = Column(DateTime(timezone=True), nullable=True)

    # Referred user (populates on conversion)
    referred_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    referred_email = Column(String(255), nullable=True)
    conversion_at = Column(DateTime(timezone=True), nullable=True, index=True)


class ReferralDiscount(Base):
    """
    Discount code linked to referral share
    20% off for referred users
    """
    __tablename__ = "referral_discounts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    share_id = Column(
        UUID(as_uuid=True),
        ForeignKey("referral_shares.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    discount_code = Column(String(50), unique=True, nullable=False, index=True)
    stripe_coupon_id = Column(String(255), nullable=True)

    discount_percent = Column(Integer, nullable=False, default=20)

    valid_from = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    valid_until = Column(DateTime(timezone=True), nullable=False)

    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    applied_count = Column(Integer, nullable=False, default=0)


class OGImageGeneration(Base):
    """
    Track async OG image generation for shares
    Status: pending, processing, completed, failed
    """
    __tablename__ = "og_image_generation"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scan_id = Column(
        UUID(as_uuid=True),
        ForeignKey("analysis_results.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )

    status = Column(String(50), nullable=False, default="pending")  # pending, processing, completed, failed
    bucket_path = Column(String(255), nullable=True)
    image_url = Column(Text, nullable=True)
    fallback_used = Column(Integer, nullable=False, default=False)  # Boolean

    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    retry_count = Column(Integer, nullable=False, default=0)


class EmailBounce(Base):
    """
    Track bounced emails (Resend webhook)
    Prevents future sends to invalid addresses
    """
    __tablename__ = "email_bounces"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), nullable=False, index=True)
    bounce_type = Column(String(50), nullable=True)  # 'permanent', 'temporary'
    bounce_reason = Column(Text, nullable=True)
    resend_bounce_id = Column(String(255), unique=True, nullable=True)

    flagged_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class ReferralEvent(Base):
    """
    Audit log for all referral events (PostHog tracking)
    Events: share_created, share_viewed, share_converted, discount_applied
    """
    __tablename__ = "referral_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    event_type = Column(String(50), nullable=False, index=True)  # share_created, share_viewed, etc.
    user_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    email = Column(String(255), nullable=True)

    share_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    scan_id = Column(UUID(as_uuid=True), nullable=True, index=True)

    posthog_event_id = Column(String(255), unique=True, nullable=True)

    event_metadata = Column(JSONB, nullable=False, default={})  # Renamed from 'metadata' (SQLAlchemy reserved)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, index=True)


# ---------------------------------------------------------------------------
# Phase 2: Stripe Webhook Tables (Deduplication, Audit, DLQ)
# ---------------------------------------------------------------------------

class ProcessedStripeEvent(Base):
    """
    Deduplication table for Stripe webhook events.
    
    Prevents double-processing (and double-charging) if webhook is retried.
    Uses unique constraint on event_id.
    """
    __tablename__ = "processed_stripe_events"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    event_id = Column(String(255), nullable=False, unique=True, index=True)
    event_type = Column(String(100), nullable=False)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    webhook_payload = Column(JSONB, nullable=False)
    idempotency_key = Column(String(255), nullable=True)
    
    processed_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )


class StripeWebhookEvent(Base):
    """
    Full audit trail of all Stripe webhook events (for dispute resolution).
    
    Maintained for compliance (7 years minimum).
    """
    __tablename__ = "stripe_webhook_events"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    event_id = Column(String(255), nullable=False, index=True)
    event_type = Column(String(100), nullable=False)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    event_data = Column(JSONB, nullable=False)
    status = Column(String(50), nullable=False)  # 'success', 'failure', 'skipped', 'dedup'
    error_message = Column(Text, nullable=True)
    http_status_code = Column(Integer, nullable=True)
    processing_duration_ms = Column(Integer, nullable=True)
    
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )


class FailedEmailRetry(Base):
    """
    Dead Letter Queue (DLQ) for failed email sends.
    
    If Resend fails or ARQ is down, email payload stored here.
    Recovery worker retries up to 3 times with exponential backoff.
    """
    __tablename__ = "failed_email_retry"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    email_type = Column(String(50), nullable=False)  # 'welcome_pro', 'fear_notification'
    email_address = Column(String(255), nullable=False)
    payload = Column(JSONB, nullable=False)
    
    # Retry tracking
    retry_count = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=True)
    
    # Scheduling
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )
    next_retry_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )
    last_retry_at = Column(DateTime(timezone=True), nullable=True)
    
    # Resolution tracking
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolved_status = Column(String(50), nullable=True)  # 'sent', 'abandoned', 'bounced'
    last_http_code = Column(Integer, nullable=True)


# ---------------------------------------------------------------------------
# Phase 5: User Preferences (Email opt-ins, Notifications, Settings)
# ---------------------------------------------------------------------------

class UserPreferences(Base):
    """
    User preferences table for flexible settings management.
    Tracks email opt-ins, notification settings, timezone, language, etc.
    """
    __tablename__ = "user_preferences"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    
    # Email preferences
    email_health_check_opted_in = Column(Boolean, nullable=False, default=False)  # Monthly resume health emails
    last_health_check_sent_date = Column(Date, nullable=True)  # Track last send to avoid duplicates
    
    # Localization
    language = Column(String(10), nullable=False, default="en")  # 'en', 'es', 'fr', etc.
    timezone = Column(String(50), nullable=False, default="UTC")  # e.g., 'America/New_York'
    
    # Global notification toggle
    notifications_enabled = Column(Boolean, nullable=False, default=True)
    
    # Timestamps
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )


# ============================================================================
# PHASE 1: EMAIL AUTOMATION MODELS
# ============================================================================

class NudgeTracking(Base):
    """Track all nudge emails (fear, abandoned, digest)"""
    __tablename__ = "nudge_tracking"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    analysis_session_id = Column(String(255), nullable=False)
    
    nudge_type = Column(String(50), nullable=False)  # 'fear', 'abandoned', 'digest'
    
    scheduled_at = Column(DateTime(timezone=True))
    sent_at = Column(DateTime(timezone=True))
    opened_at = Column(DateTime(timezone=True))
    clicked_at = Column(DateTime(timezone=True))
    converted_at = Column(DateTime(timezone=True))
    
    email_subject = Column(Text)
    template_id = Column(String(100))
    
    gemini_cost_cents = Column(Integer, default=0)
    resend_cost_cents = Column(Integer, default=1)
    
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


class GeminiCostLog(Base):
    """Track all Gemini API calls for cost monitoring"""
    __tablename__ = "gemini_cost_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    operation_type = Column(String(50), index=True)
    tokens_input = Column(Integer)
    tokens_output = Column(Integer)
    cost_cents = Column(Integer)
    
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    session_id = Column(String(255))
    error_message = Column(Text)
    
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, index=True)


# ============================================================================
# PHASE 2: AI AGENT MODELS
# ============================================================================

class AgentExecution(Base):
    """Track all agent runs"""
    __tablename__ = "agent_executions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    agent_type = Column(String(50), index=True)  # 'coach', 'tailor', 'interview'
    session_id = Column(String(255), index=True)
    user_goal = Column(Text)
    tools_called = Column(JSONB, default={})
    
    execution_time_seconds = Column(Integer)
    gemini_input_tokens = Column(Integer, default=0)
    gemini_output_tokens = Column(Integer, default=0)
    gemini_cost_cents = Column(Integer, default=0)
    
    user_rating = Column(Integer)  # 1-5
    feedback_text = Column(Text)
    error_message = Column(Text)
    
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, index=True)


class AgentSubscription(Base):
    """Track user access to agents"""
    __tablename__ = "agent_subscriptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    agent_type = Column(String(50))  # 'coach', 'tailor', 'interview'
    tier_level = Column(String(50), default="free")  # 'free', 'pro', 'pro_max'
    
    sessions_remaining = Column(Integer, default=1)  # -1 = unlimited
    last_reset_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    expires_at = Column(DateTime(timezone=True))
    
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class JobDescriptionCache(Base):
    """Cache scraped JDs to avoid re-scraping"""
    __tablename__ = "job_description_cache"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    url_hash = Column(String(64), unique=True, index=True)
    url = Column(Text)
    job_description = Column(Text)
    source = Column(String(50))
    
    scraped_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    expires_at = Column(DateTime(timezone=True))


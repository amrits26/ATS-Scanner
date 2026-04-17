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
    Float,
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

    # Trial tracking
    trial_ends_at = Column(DateTime(timezone=True), nullable=True)  # Non-null = active trial

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

    # Relationships
    analyses = relationship(
        "AnalysisResult",
        back_populates="user",
        lazy="select",
        order_by="AnalysisResult.created_at.desc()",
    )
    
    # Referral program relationships
    referral_code = relationship(
        "ReferralCode",
        back_populates="user",
        uselist=False,
        lazy="select"
    )
    referrals_made = relationship(
        "ReferralConversion",
        foreign_keys="ReferralConversion.referrer_id",
        back_populates="referrer",
        lazy="select"
    )
    referred_by = relationship(
        "ReferralConversion",
        foreign_keys="ReferralConversion.referred_user_id",
        back_populates="referred_user",
        uselist=False,
        lazy="select"
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

    # Cached top-level ATS score for fast percentile queries (extracted from result_json)
    final_ats_score = Column(Float, nullable=True, index=True)

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


# ---------------------------------------------------------------------------
# Phase 7: AI Job Hunter (Job Scraping + Tailored Resume Workspace)
# ---------------------------------------------------------------------------

class Job(Base):
    """
    Scraped job listings for Job Hunter feature.
    Used by JobHunterDashboard to display available jobs for resume tailoring.
    """
    __tablename__ = "jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    external_id = Column(String(255), nullable=True, index=True)  # Unique ID from job source
    
    # Job metadata
    title = Column(String(255), nullable=False, index=True)
    company = Column(String(255), nullable=False, index=True)
    location = Column(String(255), nullable=False, index=True)
    country_code = Column(String(2), nullable=False, default="US", index=True)  # US, CA, AU, etc.
    
    # Compensation  
    salary_min = Column(Integer, nullable=True)  # In thousands (e.g. 80 = $80k)
    salary_max = Column(Integer, nullable=True)  # In thousands
    currency = Column(String(3), nullable=False, default="USD")
    
    # Full job description for tailoring
    description = Column(Text, nullable=False)
    description_hash = Column(String(64), nullable=True, index=True)  # For deduplication
    
    # Visa sponsorship / Remote status
    visa_sponsorship = Column(Boolean, nullable=False, default=False)
    remote = Column(Boolean, nullable=False, default=False)
    
    # Source metadata
    source = Column(String(50), nullable=False)  # 'indeed', 'linkedin', 'hackernews'
    source_url = Column(Text, nullable=True)
    posted_date = Column(DateTime(timezone=True), nullable=True)
    
    # Extracted keywords via Auditor service (JSONB cache for fast searches)
    skill_rubric = Column(JSONB, nullable=True)  # {"hard_skills": [...], "soft_skills": [...], ...}
    
    # Job Hunter tracking
    view_count = Column(Integer, nullable=False, default=0)
    tailored_count = Column(Integer, nullable=False, default=0)  # How many resumes have been tailored for this
    
    # Phase 7: Visa sponsorship probability (trained on US DOL data)
    visa_probability = Column(Float, nullable=True, default=0.5)  # 0-1.0: likelihood of H1B sponsorship
    
    # Expiration & deduplication
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    expired_at = Column(DateTime(timezone=True), nullable=True)
    
    # Timestamps
    scraped_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class TailorRewritePurchase(Base):
    """
    Tracks $29 one-time Tailor Agent rewrite purchases.
    Created on checkout, updated after Stripe webhook + ARQ rewrite job.
    """
    __tablename__ = "tailor_rewrite_purchases"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    email = Column(String(255), nullable=False)
    job_description_snippet = Column(Text, nullable=True)
    resume_text = Column(Text, nullable=True)  # Original resume for diff view
    rewritten_resume_text = Column(Text, nullable=True)
    download_url = Column(String(500), nullable=True)
    stripe_payment_id = Column(String(255), unique=True, nullable=True)
    amount_cents = Column(Integer, nullable=False, default=2900)
    status = Column(String(50), nullable=False, default="pending")
    before_ats_score = Column(Integer, nullable=True)
    after_ats_score = Column(Integer, nullable=True)
    downloaded_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class TailoredResume(Base):
    """
    Stores tailored resumes for audit trail and re-use.
    Indexed by (user_id, job_id) for quick retrieval.
    """
    __tablename__ = "tailored_resumes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    job_id = Column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Tailoring pipeline results
    original_resume = Column(Text, nullable=False)  # User's original resume text
    tailored_resume = Column(Text, nullable=False)  # After Tailor service
    
    # Three-step pipeline scores
    auditor_result = Column(JSONB, nullable=True)  # SkillRubric from Auditor
    grader_result = Column(JSONB, nullable=True)  # GradeResult from Grader {score, passed, feedback}
    
    # Phase 7: Enhanced metrics for "Million-Dollar ATS"
    semantic_similarity = Column(Float, nullable=True)  # 0-100 embedding cosine similarity
    match_tier = Column(String(50), nullable=True)  # "Strong Match", "Potential Fit", "Partial Overlap"
    missing_signals = Column(JSONB, nullable=True)  # List of {term, category, confidence} gaps
    hit_rate = Column(Float, nullable=True)  # % of required terms found (0-1.0)
    overall_fit = Column(String(500), nullable=True)  # One-line semantic assessment
    
    # Impact transformation metrics
    impact_score = Column(Float, nullable=True)  # 0-100 based on STAR method + metrics
    bullet_improvements = Column(JSONB, nullable=True)  # [{original, rewritten, impact_level}, ...]
    
    # Parsing health check
    parsing_health = Column(JSONB, nullable=True)  # {status: ok|warning, issues: [...]}
    
    # Status tracking
    status = Column(String(50), nullable=False, default="pending")  # pending, tailored, graded, failed
    retry_count = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=True)
    
    # User actions
    downloaded_at = Column(DateTime(timezone=True), nullable=True)
    downloaded_format = Column(String(20), nullable=True)  # 'docx', 'pdf', 'text'
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


# ---------------------------------------------------------------------------
# Phase 7 Revenue: Referral Program
# ---------------------------------------------------------------------------

class ReferralCode(Base):
    """
    User referral codes for viral growth program.
    One per user, tracks clicks and signups.
    """
    __tablename__ = "referral_codes"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True
    )
    code = Column(String(50), unique=True, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    
    # Viral tracking
    clicks = Column(Integer, nullable=False, default=0)
    signups = Column(Integer, nullable=False, default=0)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationship
    user = relationship("User", back_populates="referral_code", lazy="select")


class ReferralConversion(Base):
    """
    Track successful referral conversions and commissions.
    Links referrer to referred user with conversion details.
    """
    __tablename__ = "referral_conversions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    referrer_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    referred_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True
    )
    referral_code_used = Column(String(50), nullable=False)
    conversion_date = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    
    # Subscription details at time of conversion
    subscription_tier = Column(String(20), nullable=True)  # pro, premium
    commission_rate = Column(Float, nullable=False, default=0.20)  # 20% default
    commission_amount = Column(Float, nullable=False, default=0.0)  # Dollar amount
    
    # Subscription tracking
    status = Column(String(20), nullable=False, default="active")  # active, canceled, refunded
    stripe_subscription_id = Column(String(100), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    referrer = relationship(
        "User",
        foreign_keys=[referrer_id],
        back_populates="referrals_made",
        lazy="select"
    )
    referred_user = relationship(
        "User",
        foreign_keys=[referred_user_id],
        back_populates="referred_by",
        lazy="select"
    )


# ---------------------------------------------------------------------------
# Phase 8: Autonomous Job Agent + Resume Architect
# ---------------------------------------------------------------------------

class JobAgent(Base):
    """
    Saved job search agent. Runs on a schedule to discover new jobs and
    optionally match + email digest to the user.
    """
    __tablename__ = "job_agents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(String(255), nullable=False)
    query = Column(String(500), nullable=False)
    location = Column(String(255), nullable=True)
    country_code = Column(String(2), nullable=False, default="US")
    visa_sponsorship = Column(Boolean, nullable=False, default=False)
    remote_only = Column(Boolean, nullable=False, default=False)
    salary_min = Column(Integer, nullable=True)
    base_resume_text = Column(Text, nullable=True)
    email_digest_enabled = Column(Boolean, nullable=False, default=True)
    frequency = Column(String(20), nullable=False, default="daily")  # daily, weekly
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    last_run_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    user = relationship("User", lazy="select")
    results = relationship("JobAgentResult", back_populates="agent", lazy="select")


class JobAgentResult(Base):
    """
    A single job discovered (and optionally scored) by a JobAgent run.
    """
    __tablename__ = "job_agent_results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_agent_id = Column(
        UUID(as_uuid=True),
        ForeignKey("job_agents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    job_id = Column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    match_score = Column(Float, nullable=True)
    match_tier = Column(String(50), nullable=True)
    missing_signals = Column(JSONB, nullable=True)
    was_emailed = Column(Boolean, nullable=False, default=False)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        index=True,
    )

    agent = relationship("JobAgent", back_populates="results")
    job = relationship("Job", lazy="select")


class ArchitectSession(Base):
    """
    Interactive Resume Architect session.
    GapAnalyzerAgent surfaces gaps → user answers questions → AutoTailor rewrites.
    """
    __tablename__ = "architect_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    job_id = Column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    base_resume = Column(Text, nullable=False)
    gaps = Column(JSONB, nullable=True)          # GapAnalyzerAgent output
    questions = Column(JSONB, nullable=True)     # Questions posed to user
    user_answers = Column(JSONB, nullable=True)  # User's free-text answers
    tailored_resume = Column(Text, nullable=True)  # Final tailored output
    status = Column(
        String(30),
        nullable=False,
        default="awaiting_input",  # awaiting_input | complete
    )
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )


# ---------------------------------------------------------------------------
# Phase 9: Agent Training Pipeline (Reinforcement Learning Loop)
# ---------------------------------------------------------------------------

class AgentFeedbackLog(Base):
    """
    Detailed agent interaction log for RLHF training.
    
    Captures every agent output + user reaction (accepted, edited, rejected).
    High-rated entries feed back into few-shot prompting for future runs.
    """
    __tablename__ = "agent_feedback_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_type = Column(String(50), nullable=False, index=True)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    job_id = Column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    input_context = Column(JSONB, nullable=False)   # Resume text, JD, user prefs
    agent_output = Column(JSONB, nullable=False)     # Full agent response
    user_action = Column(String(20), nullable=False)  # accepted, edited, rejected, applied
    user_edited_output = Column(JSONB, nullable=True)  # Final version if edited
    edit_distance = Column(Float, nullable=True)     # Levenshtein ratio 0-1
    rating = Column(Integer, nullable=True)          # 1-5 star rating

    is_synthetic = Column(Boolean, nullable=False, default=False)
    use_count = Column(Integer, nullable=False, default=0)  # How many times used in few-shot
    last_used_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class AgentOutcomeFeedback(Base):
    """
    Long-term outcome feedback loop.
    
    Tracks whether agent outputs led to real-world results:
    hired, got interview, rejected, abandoned.
    """
    __tablename__ = "agent_outcome_feedback"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agent_type = Column(String(50), nullable=False)
    session_id = Column(String(100), nullable=False, index=True)
    final_outcome = Column(String(20), nullable=False)  # hired, interview, rejected, abandoned

    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=True,
        onupdate=datetime.utcnow,
    )


# ---------------------------------------------------------------------------
# Phase 9: Multi-Source Job Scraping Engine
# ---------------------------------------------------------------------------

class ScrapedJob(Base):
    """
    Jobs discovered via the multi-source scraping engine (Apify + fallbacks).
    
    Separate from the existing `jobs` table which is for user-facing listings.
    This table stores raw scraped data with enrichment (skill extraction).
    """
    __tablename__ = "scraped_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source = Column(String(50), nullable=False, index=True)  # linkedin, indeed, google_jobs, glassdoor
    external_id = Column(String(200), nullable=False)  # Platform's unique ID
    url = Column(Text, nullable=True)

    title = Column(String(500), nullable=False)
    company = Column(String(200), nullable=False, index=True)
    location = Column(String(200), nullable=True)
    description = Column(Text, nullable=True)
    description_html = Column(Text, nullable=True)

    salary_min = Column(Integer, nullable=True)
    salary_max = Column(Integer, nullable=True)
    salary_currency = Column(String(10), nullable=True)
    salary_period = Column(String(20), nullable=True)  # yearly, monthly, hourly

    job_type = Column(String(50), nullable=True)  # full-time, part-time, contract
    experience_level = Column(String(50), nullable=True)
    remote_status = Column(String(50), nullable=True)  # remote, hybrid, onsite

    posted_date = Column(DateTime(timezone=True), nullable=True, index=True)
    scraped_date = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, index=True)
    expires_date = Column(DateTime(timezone=True), nullable=True)

    company_logo_url = Column(Text, nullable=True)
    company_website = Column(Text, nullable=True)

    required_skills = Column(JSONB, nullable=True)  # Extracted by Gemini
    raw_data = Column(JSONB, nullable=True)          # Full scraped payload

    is_active = Column(Boolean, nullable=False, default=True, index=True)
    last_verified = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class JobScrapingRun(Base):
    """
    Audit log for each scraping run — tracks source, parameters, outcome.
    """
    __tablename__ = "job_scraping_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source = Column(String(50), nullable=False)
    search_query = Column(JSONB, nullable=False)
    status = Column(String(20), nullable=False, default="pending")  # pending, running, completed, failed
    jobs_found = Column(Integer, nullable=False, default=0)
    jobs_new = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )


# ---------------------------------------------------------------------------
# Phase 10: Fine-Tuning Pipeline
# ---------------------------------------------------------------------------

class FineTuningJob(Base):
    """
    Tracks fine-tuning jobs across providers (Together AI, etc.).
    Lifecycle: pending → uploading → training → completed → deployed | failed
    """
    __tablename__ = "fine_tuning_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider = Column(String(50), nullable=False)        # together, replicate, openai
    base_model = Column(String(100), nullable=False)     # e.g., meta-llama/Llama-3.2-3B-Instruct
    agent_type = Column(String(50), nullable=False)      # coach, tailor, interview, etc.

    status = Column(String(30), nullable=False, default="pending")
    provider_job_id = Column(String(200), nullable=True)
    fine_tuned_model_id = Column(String(200), nullable=True)

    training_file_url = Column(Text, nullable=True)
    examples_count = Column(Integer, default=0)

    hyperparameters = Column(JSONB, nullable=True)
    training_metrics = Column(JSONB, nullable=True)
    cost_usd = Column(Float, nullable=True)
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    created_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    is_active = Column(Boolean, default=False)

    deployments = relationship("ModelDeployment", back_populates="fine_tuning_job", lazy="select")


class ModelDeployment(Base):
    """
    Tracks which fine-tuned model is actively deployed for each agent type.
    """
    __tablename__ = "model_deployments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fine_tuning_job_id = Column(
        UUID(as_uuid=True),
        ForeignKey("fine_tuning_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    agent_type = Column(String(50), nullable=False, index=True)
    model_id = Column(String(200), nullable=False)
    provider = Column(String(50), nullable=False)

    deployment_type = Column(String(20), nullable=False, default="primary")
    is_active = Column(Boolean, nullable=False, default=True)
    rollout_percentage = Column(Integer, nullable=False, default=100)  # 1-100 for A/B rollout

    deployed_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    deactivated_at = Column(DateTime(timezone=True), nullable=True)

    performance_metrics = Column(JSONB, nullable=True)

    fine_tuning_job = relationship("FineTuningJob", back_populates="deployments", lazy="select")


# ---------------------------------------------------------------------------
# Phase 11: Master Orchestrator — Journey & Outcome Tracking
# ---------------------------------------------------------------------------

class UserJourney(Base):
    """
    Complete orchestrator session recording for DPO training.

    Each row captures one full orchestrator run: the action plan,
    every event (step start/complete/fail/feedback), and the final response.
    Successful journeys become DPO 'chosen', failed ones become 'rejected'.
    """
    __tablename__ = "user_journeys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    session_id = Column(String(255), nullable=False, index=True)
    journey_stage = Column(String(50), nullable=False, default="new")

    action_plan = Column(JSONB, nullable=False, default=[])
    journey_events = Column(JSONB, nullable=False, default=[])
    final_response = Column(JSONB, nullable=True)

    steps_completed = Column(Integer, nullable=False, default=0)
    steps_failed = Column(Integer, nullable=False, default=0)
    overall_confidence = Column(Float, nullable=False, default=0.0)
    total_cost_cents = Column(Integer, nullable=False, default=0)
    execution_time_seconds = Column(Float, nullable=False, default=0.0)

    # DPO training labels
    dpo_label = Column(String(20), nullable=True)          # 'chosen' or 'rejected'
    dpo_pair_id = Column(UUID(as_uuid=True), nullable=True)
    context_embedding_hash = Column(String(64), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    outcomes = relationship("JobApplicationOutcome", back_populates="journey", lazy="select")


class JobApplicationOutcome(Base):
    """
    Closed-loop feedback: what happened after the AI helped the user.

    Captures the full state at application time so the reward model
    can learn which (resume, JD, AI-actions) tuples lead to success.
    """
    __tablename__ = "job_application_outcomes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    journey_id = Column(
        UUID(as_uuid=True),
        ForeignKey("user_journeys.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    job_id = Column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="SET NULL"),
        nullable=True,
    )

    job_title = Column(String(500), nullable=True)
    company_name = Column(String(500), nullable=True)

    outcome = Column(String(30), nullable=False, index=True)  # applied, interview, offer, hired, rejected, ghosted, abandoned
    outcome_details = Column(JSONB, nullable=True)

    # Snapshot of AI state for reward model training
    resume_snapshot = Column(Text, nullable=True)
    jd_snapshot = Column(Text, nullable=True)
    ats_score_at_apply = Column(Float, nullable=True)
    agents_used = Column(JSONB, nullable=True)
    agent_outputs = Column(JSONB, nullable=True)

    user_satisfaction = Column(Integer, nullable=True)
    user_notes = Column(Text, nullable=True)

    applied_at = Column(DateTime(timezone=True), nullable=True)
    outcome_reported_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    reward_score = Column(Float, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    journey = relationship("UserJourney", back_populates="outcomes", lazy="select")


# ---------------------------------------------------------------------------
# Recruiter Marketplace
# ---------------------------------------------------------------------------

class RecruiterAccount(Base):
    """
    Subscription-based recruiter account.
    Separate from job-seeker User; identified by its own Supabase user ID.
    """
    __tablename__ = "recruiter_accounts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False)
    company_name = Column(String(255), nullable=True)
    full_name = Column(String(255), nullable=True)
    supabase_user_id = Column(String(255), unique=True, nullable=True)

    # Stripe billing
    stripe_customer_id = Column(String(255), nullable=True)
    subscription_tier = Column(String(50), nullable=False, default="free")
    subscription_status = Column(String(50), nullable=False, default="inactive")
    stripe_subscription_id = Column(String(255), nullable=True)
    subscription_ends_at = Column(DateTime(timezone=True), nullable=True)

    # Usage tracking
    unlocks_this_month = Column(Integer, nullable=False, default=0)
    unlock_reset_date = Column(Date, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    job_postings = relationship("RecruiterJobPosting", back_populates="recruiter", lazy="select")
    candidate_matches = relationship("RecruiterCandidateMatch", back_populates="recruiter", lazy="select")


class RecruiterJobPosting(Base):
    """A job posting submitted by a recruiter for candidate matching."""
    __tablename__ = "recruiter_job_postings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recruiter_id = Column(UUID(as_uuid=True), ForeignKey("recruiter_accounts.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=False)
    parsed_keywords = Column(JSONB, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    recruiter = relationship("RecruiterAccount", back_populates="job_postings")
    candidate_matches = relationship("RecruiterCandidateMatch", back_populates="job_posting", lazy="select")


class RecruiterCandidateMatch(Base):
    """A match between a recruiter job posting and a candidate's analysis result."""
    __tablename__ = "recruiter_candidate_matches"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recruiter_id = Column(UUID(as_uuid=True), ForeignKey("recruiter_accounts.id", ondelete="CASCADE"), nullable=False)
    job_posting_id = Column(UUID(as_uuid=True), ForeignKey("recruiter_job_postings.id", ondelete="CASCADE"), nullable=False)
    analysis_id = Column(UUID(as_uuid=True), ForeignKey("analysis_results.id", ondelete="CASCADE"), nullable=False)
    match_score = Column(Float, nullable=False)
    is_viewed = Column(Boolean, nullable=False, default=False)
    is_unlocked = Column(Boolean, nullable=False, default=False)
    unlocked_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    # Relationships
    recruiter = relationship("RecruiterAccount", back_populates="candidate_matches")
    job_posting = relationship("RecruiterJobPosting", back_populates="candidate_matches")
    analysis = relationship("AnalysisResult", lazy="select")

"""Pydantic models for API requests and responses."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# --- Job Description Analyzer ---
class JobDescriptionAnalysis(BaseModel):
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    experience_level: str = ""


# --- ATS Optimizer ---
class SectionImprovements(BaseModel):
    summary: str = ""
    experience: str = ""
    skills: str = ""


class OptimizedResumeResponse(BaseModel):
    optimized_resume: str = ""
    section_improvements: SectionImprovements = Field(default_factory=SectionImprovements)


# --- ATS Scorer ---
class ATSScoreResponse(BaseModel):
    keyword_match_percent: float = 0.0
    semantic_similarity_score: float = 0.0
    final_ats_score: float = 0.0
    missing_keywords: list[str] = Field(default_factory=list)
    recommended_keywords_to_add: list[str] = Field(default_factory=list)
    # Phase 6: Credibility layer
    percentile_rank: int | None = None  # 0-100, where user ranks
    confidence_score: int | None = None  # 0-100, confidence in score
    algorithm_breakdown: dict[str, float] | None = None  # {"keywords": 40, "format": 30, "experience": 20, "structure": 10}
    keyword_impact_data: list[dict[str, Any]] | None = None  # [{"keyword": "Python", "impact_percent": 1.8, "confidence": 0.85}, ...]


# --- Bonus: weak verbs, metrics, passive ---
class WritingFeedback(BaseModel):
    weak_verbs_detected: list[str] = Field(default_factory=list)
    bullets_without_metrics: list[str] = Field(default_factory=list)
    passive_voice_phrases: list[str] = Field(default_factory=list)
    readability_score: float = 0.0
    sections_detected: list[str] = Field(default_factory=list)


# --- Full optimization result ---
class FullOptimizationResult(BaseModel):
    optimized_resume: str = ""
    section_improvements: SectionImprovements = Field(default_factory=SectionImprovements)
    ats_score: ATSScoreResponse = Field(default_factory=ATSScoreResponse)
    jd_analysis: JobDescriptionAnalysis = Field(default_factory=JobDescriptionAnalysis)
    writing_feedback: WritingFeedback | None = None
    chart_paths: dict[str, str] = Field(default_factory=dict)


# --- Skill Gap Analysis ---
class SkillGap(BaseModel):
    """Detailed skill gap with category, relevance, and recommendation."""
    skill: str = ""
    category: str = ""  # "hard_gap", "soft_gap", or "adjacent"
    relevance_score: float = 0.0  # 1-10 scale
    recommendation: str = ""


class SkillGapAnalysis(BaseModel):
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    hard_gaps: list[SkillGap] = Field(default_factory=list)  # Technical skills
    soft_gaps: list[SkillGap] = Field(default_factory=list)  # Interpersonal/management
    adjacent_skills: list[SkillGap] = Field(default_factory=list)  # Similar to JD requirements
    gap_score: float = 0.0  # 0-100, percentage of skills matched
    match_count: int = 0
    total_required: int = 0
    critical_gaps: list[SkillGap] = Field(default_factory=list)  # Top 5 gaps by relevance


# --- Resume Quality Score ---
class ResumeQualityScore(BaseModel):
    overall_score: float = 0.0  # 0-100
    readability_score: float = 0.0
    formatting_score: float = 0.0
    content_score: float = 0.0
    keyword_density_score: float = 0.0
    feedback: list[str] = Field(default_factory=list)


# --- Keyword Heatmap ---
class KeywordHeatmapData(BaseModel):
    keywords: list[str] = Field(default_factory=list)
    frequencies: list[int] = Field(default_factory=list)
    importance_scores: list[float] = Field(default_factory=list)  # 0-1 scale


# --- Comprehensive Analysis Result ---
class ComprehensiveAnalysisResult(BaseModel):
    original_resume: str = ""
    optimized_resume: str = ""
    ats_score: ATSScoreResponse = Field(default_factory=ATSScoreResponse)
    jd_analysis: JobDescriptionAnalysis = Field(default_factory=JobDescriptionAnalysis)
    skill_gap: SkillGapAnalysis | None = Field(default=None)  # Can be None for free users
    resume_quality: ResumeQualityScore | None = Field(default=None)  # Can be None for free users
    keyword_heatmap: KeywordHeatmapData | None = Field(default=None)  # Can be None for free users
    writing_feedback: WritingFeedback | None = None
    chart_paths: dict[str, str] = Field(default_factory=dict)


# =============================================================================
# SaaS Layer — User, Tier, Analysis Status
# =============================================================================

class UserTierEnum(str, Enum):
    """Subscription tier for gated feature access."""
    free = "free"
    pro  = "pro"


class AnalysisStatusEnum(str, Enum):
    """Async processing state for a scan job."""
    pending    = "pending"
    processing = "processing"
    completed  = "completed"
    failed     = "failed"


class UserResponse(BaseModel):
    """Public user profile returned after auth."""
    id:               str
    email:            str
    full_name:        str | None = None
    tier:             UserTierEnum = UserTierEnum.free
    scans_this_month: int = 0
    scan_limit:       int = 3   # -1 = unlimited (pro)
    created_at:       datetime


class AnalysisHistoryItem(BaseModel):
    """
    Lightweight row for the History page — avoids sending the full
    result_json for every item in the list.
    """
    session_id:      str
    status:          AnalysisStatusEnum
    resume_filename: str | None = None
    final_ats_score: float | None = None   # extracted from result_json
    created_at:      datetime


class KeywordValueItem(BaseModel):
    """Per-keyword impact breakdown"""
    keyword: str = ""
    impact_percent: float = 0.0
    confidence: float = 0.0


class LiveKeywordData(BaseModel):
    """
    AI War Room: Real-time intelligence feed with scoring transformation
    Shows keywords + score impact + AI confidence + conversion psychology
    """
    # Original keyword data
    keywords_found: int = 0
    keywords_added: int = 0
    top_added: list[str] = Field(default_factory=list)
    predicted_boost: float = 0.0
    status_message: str = ""
    free_tier_preview: list[str] = Field(default_factory=list)
    locked_keywords_count: int = 0
    
    # Score transformation (before/after)
    before_score: float = 0.0
    after_score_predicted: float = 0.0
    match_percentage: float = 0.0
    competitor_avg_score: float = 22.0
    
    # AI action feed (real-time pipeline transparency)
    current_step: int = 0
    step_action: str = ""
    time_elapsed_seconds: int = 0
    ai_confidence: float = 0.0
    
    # Per-keyword breakdown + steps log
    keyword_values: list[KeywordValueItem] = Field(default_factory=list)
    steps_log: list[str] = Field(default_factory=list)


class AnalysisPollResponse(BaseModel):
    """
    Returned by GET /api/analysis/{session_id}/status.
    While pending/processing, result is None.
    When completed, result contains the (possibly tier-gated) payload.
    
    Phase 1 Enhancement: Includes step-level progress tracking + live keywords
    Phase 3 Enhancement: Includes og_image_ready for share feature readiness
    """
    session_id:    str
    status:        AnalysisStatusEnum
    # --- Step-level progress (Phase 1: The Engine) ---
    current_step:  int = 0  # 0-10 (0=pending, 1-8=analysis steps, 9-10=post-processing)
    step_message:  str = ""  # e.g., "Step 3/8: Analyzing Job Description..."
    progress_percent: int = 0  # 0-100
    estimated_remaining_seconds: int = 0  # Estimated time left
    # --- Phase 1: Real-Time Keywords ---
    live_keywords: LiveKeywordData | None = None  # Live keyword feed during optimization
    # --- Sharing ---
    og_image_ready: bool = False  # True = OG image generated & ready for LinkedIn share
    # --- Results ---
    result:        ComprehensiveAnalysisResult | None = None
    error_message: str | None = None


class AsyncScanAccepted(BaseModel):
    """Immediate 202 Accepted response when a scan job is queued."""
    session_id: str
    status:     AnalysisStatusEnum = AnalysisStatusEnum.pending
    poll_url:   str   # e.g. /api/analysis/{session_id}/status


# ---------------------------------------------------------------------------
# Stripe Scaffold
# ---------------------------------------------------------------------------

class StripeCheckoutRequest(BaseModel):
    """
    Request body for POST /api/payments/create-checkout.
    TODO: populate price_id from STRIPE_PRO_PRICE_ID env var if not provided.
    """
    price_id:    str | None = None
    success_url: str = "http://localhost:5173/dashboard?upgraded=true"
    cancel_url:  str = "http://localhost:5173/pricing"


class StripeCheckoutResponse(BaseModel):
    """URL to redirect the user to Stripe's hosted checkout page."""
    checkout_url: str
    session_id:   str


# ---------------------------------------------------------------------------
# Phase 3: The Feedback Loop — Model Training
# ---------------------------------------------------------------------------

class FeedbackRequest(BaseModel):
    """
    Phase 3: User feedback on analysis accuracy
    Used to train and improve AI model prompts
    """
    score_accuracy: int = Field(ge=1, le=5)  # 1-5 scale: how accurate was the ATS score?
    was_helpful: bool  # Did this analysis help you?
    user_notes: str | None = None  # Optional free-text feedback


class FeedbackResponse(BaseModel):
    """Response after feedback is recorded."""
    status: str = "recorded"
    message: str = "The machine is learning from your feedback."

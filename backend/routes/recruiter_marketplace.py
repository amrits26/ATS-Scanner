"""
Recruiter Marketplace Routes

B2B revenue pillar — recruiter signup, job postings, candidate matching.

Endpoints:
  POST /api/recruiter-marketplace/signup           — Create account + Stripe checkout
  GET  /api/recruiter-marketplace/me               — Current recruiter profile
  POST /api/recruiter-marketplace/jobs              — Create a job posting
  GET  /api/recruiter-marketplace/jobs              — List recruiter's job postings
  GET  /api/recruiter-marketplace/matches           — Anonymized candidate matches
  POST /api/recruiter-marketplace/matches/{id}/unlock — Unlock contact info
"""

import logging
import os
from datetime import datetime
from typing import List, Optional
from uuid import UUID

import stripe
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import get_current_recruiter
from backend.database import get_db
from backend.db_models import (
    AnalysisResult,
    RecruiterAccount,
    RecruiterCandidateMatch,
    RecruiterJobPosting,
    User,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/recruiter-marketplace", tags=["recruiter-marketplace"])

stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
RECRUITER_BASIC_PRICE_ID = os.getenv("STRIPE_RECRUITER_BASIC_PRICE_ID", "")
RECRUITER_PRO_PRICE_ID = os.getenv("STRIPE_RECRUITER_PRO_PRICE_ID", "")

# Unlock limits per tier per month
UNLOCK_LIMITS = {"free": 0, "basic": 5, "pro": -1}  # -1 = unlimited


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class RecruiterSignupRequest(BaseModel):
    email: EmailStr
    company_name: str = Field(..., max_length=255)
    full_name: Optional[str] = Field(None, max_length=255)
    tier: str = Field("basic", pattern="^(basic|pro)$")


class RecruiterProfileResponse(BaseModel):
    id: str
    email: str
    company_name: Optional[str]
    subscription_tier: str
    subscription_status: str
    unlocks_this_month: int
    unlock_limit: int  # -1 = unlimited


class JobPostingCreate(BaseModel):
    title: str = Field(..., max_length=500)
    description: str = Field(..., min_length=50)


class JobPostingResponse(BaseModel):
    id: str
    title: str
    match_count: int = 0
    is_active: bool
    created_at: datetime


class CandidateMatchResponse(BaseModel):
    match_id: str
    match_score: float
    job_title: str
    candidate_skills: List[str]
    resume_highlights: List[str]
    is_unlocked: bool
    created_at: datetime


class UnlockedContactResponse(BaseModel):
    candidate_name: Optional[str]
    candidate_email: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/signup")
async def recruiter_signup(
    request: RecruiterSignupRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create recruiter account and redirect to Stripe checkout."""
    # Check duplicate
    existing = await db.execute(
        select(RecruiterAccount).where(RecruiterAccount.email == request.email)
    )
    if existing.scalars().first():
        raise HTTPException(status_code=400, detail="Email already registered as recruiter")

    # Stripe customer
    customer = stripe.Customer.create(
        email=request.email,
        metadata={"company": request.company_name, "role": "recruiter"},
    )

    # Pick price
    price_id = RECRUITER_BASIC_PRICE_ID if request.tier == "basic" else RECRUITER_PRO_PRICE_ID
    if not price_id:
        raise HTTPException(status_code=503, detail="Recruiter pricing not configured")

    session = stripe.checkout.Session.create(
        customer=customer.id,
        payment_method_types=["card"],
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        subscription_data={
            "trial_period_days": 7,
            "metadata": {"email": request.email, "tier": request.tier, "role": "recruiter"},
        },
        success_url=f"{FRONTEND_URL}/recruiter?signup=success",
        cancel_url=f"{FRONTEND_URL}/recruiter/signup?canceled=true",
        metadata={"email": request.email, "tier": request.tier, "role": "recruiter"},
    )

    # Create account (inactive until Stripe webhook confirms)
    acct = RecruiterAccount(
        email=request.email,
        company_name=request.company_name,
        full_name=request.full_name,
        stripe_customer_id=customer.id,
        subscription_tier=request.tier,
        subscription_status="pending",
    )
    db.add(acct)
    await db.commit()

    logger.info(f"[RECRUITER] Signup initiated: {request.email} ({request.tier})")
    return {"checkout_url": session.url}


@router.get("/me", response_model=RecruiterProfileResponse)
async def recruiter_profile(
    recruiter: RecruiterAccount = Depends(get_current_recruiter),
):
    """Get current recruiter's profile and usage."""
    limit = UNLOCK_LIMITS.get(recruiter.subscription_tier, 0)
    return RecruiterProfileResponse(
        id=str(recruiter.id),
        email=recruiter.email,
        company_name=recruiter.company_name,
        subscription_tier=recruiter.subscription_tier,
        subscription_status=recruiter.subscription_status,
        unlocks_this_month=recruiter.unlocks_this_month,
        unlock_limit=limit,
    )


# ---------------------------------------------------------------------------
# Job Postings
# ---------------------------------------------------------------------------

@router.post("/jobs", response_model=JobPostingResponse)
async def create_job_posting(
    request: JobPostingCreate,
    recruiter: RecruiterAccount = Depends(get_current_recruiter),
    db: AsyncSession = Depends(get_db),
):
    """Create a job posting. Active subscriptions only."""
    if recruiter.subscription_status not in ("active", "trialing"):
        raise HTTPException(status_code=403, detail="Active subscription required to post jobs")

    # Tier-based limits: basic = 10 active, pro = unlimited
    if recruiter.subscription_tier == "basic":
        active_count_res = await db.execute(
            select(func.count(RecruiterJobPosting.id))
            .where(RecruiterJobPosting.recruiter_id == recruiter.id)
            .where(RecruiterJobPosting.is_active == True)
        )
        if active_count_res.scalar_one() >= 10:
            raise HTTPException(status_code=403, detail="Basic tier limited to 10 active job postings")

    job = RecruiterJobPosting(
        recruiter_id=recruiter.id,
        title=request.title,
        description=request.description,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    logger.info(f"[RECRUITER] Job posted: {job.title} by {recruiter.email}")
    return JobPostingResponse(
        id=str(job.id),
        title=job.title,
        match_count=0,
        is_active=job.is_active,
        created_at=job.created_at,
    )


@router.get("/jobs", response_model=List[JobPostingResponse])
async def list_job_postings(
    recruiter: RecruiterAccount = Depends(get_current_recruiter),
    db: AsyncSession = Depends(get_db),
):
    """List all job postings for the current recruiter."""
    result = await db.execute(
        select(RecruiterJobPosting)
        .where(RecruiterJobPosting.recruiter_id == recruiter.id)
        .order_by(RecruiterJobPosting.created_at.desc())
    )
    jobs = result.scalars().all()

    response = []
    for job in jobs:
        match_count_res = await db.execute(
            select(func.count(RecruiterCandidateMatch.id))
            .where(RecruiterCandidateMatch.job_posting_id == job.id)
        )
        response.append(JobPostingResponse(
            id=str(job.id),
            title=job.title,
            match_count=match_count_res.scalar_one(),
            is_active=job.is_active,
            created_at=job.created_at,
        ))
    return response


# ---------------------------------------------------------------------------
# Candidate Matches
# ---------------------------------------------------------------------------

@router.get("/matches", response_model=List[CandidateMatchResponse])
async def get_candidate_matches(
    job_posting_id: Optional[str] = Query(None),
    min_score: float = Query(70.0, ge=0, le=100),
    limit: int = Query(20, ge=1, le=100),
    recruiter: RecruiterAccount = Depends(get_current_recruiter),
    db: AsyncSession = Depends(get_db),
):
    """Get anonymized candidate matches, ordered by score."""
    query = (
        select(RecruiterCandidateMatch)
        .where(RecruiterCandidateMatch.recruiter_id == recruiter.id)
        .where(RecruiterCandidateMatch.match_score >= min_score)
        .order_by(RecruiterCandidateMatch.match_score.desc())
        .limit(limit)
    )
    if job_posting_id:
        query = query.where(RecruiterCandidateMatch.job_posting_id == job_posting_id)

    result = await db.execute(query)
    matches = result.scalars().all()

    response = []
    for match in matches:
        # Fetch analysis for anonymized data
        analysis_res = await db.execute(
            select(AnalysisResult).where(AnalysisResult.id == match.analysis_id)
        )
        analysis = analysis_res.scalars().first()
        if not analysis:
            continue

        result_json = analysis.result_json or {}
        ats_data = result_json.get("ats_score", {})
        skill_gap = result_json.get("skill_gap", {})

        response.append(CandidateMatchResponse(
            match_id=str(match.id),
            match_score=float(match.match_score),
            job_title=result_json.get("jd_analysis", {}).get("detected_job_title", "Unknown"),
            candidate_skills=skill_gap.get("matched_skills", [])[:5],
            resume_highlights=[
                f"ATS Score: {ats_data.get('final_ats_score', 0):.0f}/100",
                f"Matched {len(skill_gap.get('matched_skills', []))} skills",
                f"Missing {len(skill_gap.get('missing_skills', []))} skills",
            ],
            is_unlocked=match.is_unlocked,
            created_at=match.created_at,
        ))

    return response


@router.post("/matches/{match_id}/unlock", response_model=UnlockedContactResponse)
async def unlock_candidate(
    match_id: str,
    recruiter: RecruiterAccount = Depends(get_current_recruiter),
    db: AsyncSession = Depends(get_db),
):
    """Unlock candidate contact info. Pro = unlimited, Basic = 5/month."""
    # Verify match belongs to this recruiter
    match_res = await db.execute(
        select(RecruiterCandidateMatch)
        .where(RecruiterCandidateMatch.id == match_id)
        .where(RecruiterCandidateMatch.recruiter_id == recruiter.id)
    )
    match = match_res.scalars().first()
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")

    if match.is_unlocked:
        # Already unlocked — return contact info again
        pass
    else:
        # Check unlock budget
        limit = UNLOCK_LIMITS.get(recruiter.subscription_tier, 0)
        if limit == 0:
            raise HTTPException(status_code=403, detail="Subscription required to unlock candidates")
        if limit > 0 and recruiter.unlocks_this_month >= limit:
            raise HTTPException(
                status_code=403,
                detail=f"Monthly unlock limit reached ({limit}). Upgrade to Pro for unlimited.",
            )

        # Mark unlocked
        match.is_unlocked = True
        match.unlocked_at = datetime.utcnow()
        recruiter.unlocks_this_month += 1
        await db.commit()

    # Resolve candidate contact from analysis → user
    analysis_res = await db.execute(
        select(AnalysisResult).where(AnalysisResult.id == match.analysis_id)
    )
    analysis = analysis_res.scalars().first()
    if not analysis or not analysis.user_id:
        raise HTTPException(status_code=404, detail="Candidate data not available")

    user_res = await db.execute(select(User).where(User.id == analysis.user_id))
    user = user_res.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="Candidate user not found")

    logger.info(f"[RECRUITER] Contact unlocked: match={match_id} by {recruiter.email}")
    return UnlockedContactResponse(
        candidate_name=user.full_name,
        candidate_email=user.email,
    )

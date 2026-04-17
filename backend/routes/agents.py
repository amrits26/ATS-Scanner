"""
Agent API Routes - Endpoints for all AI agents

Pattern: POST /api/agent/{agent_type} -> returns response
"""

import uuid
import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.auth import get_current_user
from backend.db_models import User
from backend.services.agent_coach import ResumeCoachAgent
from backend.services.agent_tailor import AutoTailorAgent
from backend.services.agent_interview import InterviewPrepAgent
from backend.services.agent_telemetry import AgentTelemetry

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/agent", tags=["AI Agents"])


# ========================================================================
# Request Models
# ========================================================================

class CoachRequest(BaseModel):
    question: str
    resume_text: str
    target_job_description: Optional[str] = None
    session_id: Optional[str] = None


class TailorRequest(BaseModel):
    resume_text: str
    job_url: Optional[str] = None
    jd_text: Optional[str] = None


class InterviewRequest(BaseModel):
    job_title: str
    company: str
    resume_text: Optional[str] = None
    session_id: Optional[str] = None


# ========================================================================
# Endpoints
# ========================================================================

@router.post("/coach")
async def coach_endpoint(
    request: CoachRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Start a Resume Coach session.
    Returns result with execution details.
    """
    session_id = request.session_id or str(uuid.uuid4())

    try:
        telemetry = AgentTelemetry(db)
        
        # Budget gate: block if monthly spend exceeded
        within_budget, remaining = await telemetry.check_monthly_budget(str(current_user.id))
        if not within_budget:
            raise HTTPException(
                status_code=402,
                detail=f"Monthly AI budget exceeded. Remaining: ${remaining/100:.2f}. Resets next month.",
            )
        
        agent = ResumeCoachAgent(
            user_id=str(current_user.id),
            session_id=session_id,
            telemetry_tracker=telemetry,
        )
        
        context = {
            "resume_text": request.resume_text,
            "job_description": request.target_job_description,
        }
        
        result = await agent.execute(request.question, context)

        return {
            "session_id": session_id,
            "status": result["status"],
            "response": result.get("response"),
            "execution_time_seconds": result.get("execution_time_seconds"),
            "gemini_cost_cents": result.get("gemini_cost_cents"),
        }

    except Exception as e:
        logger.error(f"[COACH] Endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tailor")
async def tailor_endpoint(
    request: TailorRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Rewrite resume for specific job.
    """
    session_id = str(uuid.uuid4())

    try:
        telemetry = AgentTelemetry(db)
        
        # Budget gate: block if monthly spend exceeded
        within_budget, remaining = await telemetry.check_monthly_budget(str(current_user.id))
        if not within_budget:
            raise HTTPException(
                status_code=402,
                detail=f"Monthly AI budget exceeded. Remaining: ${remaining/100:.2f}. Resets next month.",
            )
        
        agent = AutoTailorAgent(
            user_id=str(current_user.id),
            session_id=session_id,
            telemetry_tracker=telemetry,
        )
        
        context = {
            "resume_text": request.resume_text,
            "job_url": request.job_url,
            "jd_text": request.jd_text,
        }
        
        result = await agent.execute("rewrite_resume_for_job", context)

        return {
            "session_id": session_id,
            "status": result["status"],
            "rewritten_resume": result.get("response", {}).get("rewritten_resume"),
            "key_alignments": result.get("response", {}).get("key_alignments", []),
            "match_score": result.get("response", {}).get("score", 0),
            "execution_time_seconds": result.get("execution_time_seconds"),
            "gemini_cost_cents": result.get("gemini_cost_cents"),
        }

    except Exception as e:
        logger.error(f"[TAILOR] Endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/interview-prep")
async def interview_prep_endpoint(
    request: InterviewRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate interview questions and STAR answers.
    """
    session_id = request.session_id or str(uuid.uuid4())

    try:
        telemetry = AgentTelemetry(db)
        
        # Budget gate: block if monthly spend exceeded
        within_budget, remaining = await telemetry.check_monthly_budget(str(current_user.id))
        if not within_budget:
            raise HTTPException(
                status_code=402,
                detail=f"Monthly AI budget exceeded. Remaining: ${remaining/100:.2f}. Resets next month.",
            )
        
        agent = InterviewPrepAgent(
            user_id=str(current_user.id),
            session_id=session_id,
            telemetry_tracker=telemetry,
        )
        
        context = {
            "job_title": request.job_title,
            "company": request.company,
            "resume_text": request.resume_text or "",
        }
        
        result = await agent.execute("prepare_interview", context)

        return {
            "session_id": session_id,
            "status": result["status"],
            "questions": result.get("response", {}),
            "execution_time_seconds": result.get("execution_time_seconds"),
            "gemini_cost_cents": result.get("gemini_cost_cents"),
        }

    except Exception as e:
        logger.error(f"[INTERVIEW] Endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Cover Letter Agent
# ============================================================================

class CoverLetterRequest(BaseModel):
    resume_text: str
    job_description: str
    company_name: str
    company_url: Optional[str] = None
    tone: str = "professional"  # professional | conversational | storytelling
    word_count: int = 350
    session_id: Optional[str] = None


@router.post("/cover-letter")
async def cover_letter_endpoint(
    request: CoverLetterRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate a personalized cover letter using the company's About page (if URL provided),
    the JD, and the user's resume.
    """
    from backend.services.agent_cover_letter import CoverLetterAgent

    session_id = request.session_id or str(uuid.uuid4())
    try:
        telemetry = AgentTelemetry(db)
        
        # Budget gate: block if monthly spend exceeded
        within_budget, remaining = await telemetry.check_monthly_budget(str(current_user.id))
        if not within_budget:
            raise HTTPException(
                status_code=402,
                detail=f"Monthly AI budget exceeded. Remaining: ${remaining/100:.2f}. Resets next month.",
            )
        
        agent = CoverLetterAgent(
            user_id=str(current_user.id),
            session_id=session_id,
            telemetry_tracker=telemetry,
        )

        # Step 1: Company research
        company_intel = await agent._company_researcher(
            company_name=request.company_name,
            company_url=request.company_url,
        )

        # Step 2: Draft letter
        draft = await agent._letter_drafter(
            resume_text=request.resume_text,
            job_description=request.job_description,
            company_intel=company_intel,
            tone=request.tone,
            word_count=request.word_count,
        )

        return {
            "session_id": session_id,
            "letter": draft.get("letter", ""),
            "subject_line": draft.get("subject_line", ""),
            "key_hooks": draft.get("key_hooks", []),
            "company_about": company_intel.get("about", ""),
            "gemini_input_tokens": agent.gemini_input_tokens,
            "gemini_output_tokens": agent.gemini_output_tokens,
        }
    except Exception as e:
        logger.error(f"[COVER-LETTER] Endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Negotiation Advisor Agent
# ============================================================================

class NegotiationRequest(BaseModel):
    job_title: str
    company: str
    location: str
    years_experience: int = 0
    current_offer: Optional[float] = None
    target_salary: Optional[float] = None
    hiring_manager_name: Optional[str] = None
    session_id: Optional[str] = None


@router.post("/negotiation")
async def negotiation_endpoint(
    request: NegotiationRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate a salary negotiation strategy, market benchmarks, and a
    ready-to-send counter-offer email + verbal talking points.
    """
    from backend.services.agent_negotiation import NegotiationAdvisorAgent

    session_id = request.session_id or str(uuid.uuid4())
    try:
        telemetry = AgentTelemetry(db)
        
        # Budget gate: block if monthly spend exceeded
        within_budget, remaining = await telemetry.check_monthly_budget(str(current_user.id))
        if not within_budget:
            raise HTTPException(
                status_code=402,
                detail=f"Monthly AI budget exceeded. Remaining: ${remaining/100:.2f}. Resets next month.",
            )
        
        agent = NegotiationAdvisorAgent(
            user_id=str(current_user.id),
            session_id=session_id,
            telemetry_tracker=telemetry,
        )

        # Step 1: Market benchmarks
        market_data = await agent._market_benchmarker(
            job_title=request.job_title,
            company=request.company,
            location=request.location,
            years_experience=request.years_experience,
            current_offer=request.current_offer,
        )

        # Step 2: Strategy
        strategy = await agent._strategy_builder(
            market_data=market_data,
            current_offer=request.current_offer,
            target_salary=request.target_salary,
            job_title=request.job_title,
            years_experience=request.years_experience,
        )

        # Step 3: Scripts
        scripts = await agent._script_generator(
            strategy=strategy,
            job_title=request.job_title,
            company=request.company,
            hiring_manager_name=request.hiring_manager_name,
        )

        return {
            "session_id": session_id,
            "market_data": market_data,
            "strategy": strategy,
            "email_subject": scripts.get("email_subject", ""),
            "email_body": scripts.get("email_body", ""),
            "talking_points": scripts.get("talking_points", []),
            "one_liner_counter": scripts.get("one_liner_counter", ""),
            "gemini_input_tokens": agent.gemini_input_tokens,
            "gemini_output_tokens": agent.gemini_output_tokens,
        }
    except Exception as e:
        logger.error(f"[NEGOTIATION] Endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

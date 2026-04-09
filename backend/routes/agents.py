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

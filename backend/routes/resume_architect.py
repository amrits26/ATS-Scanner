"""
Resume Architect Routes – Interactive gap-analysis-then-tailor pipeline.

Flow (two-call REST):
  POST /api/architect/start          → GapAnalyzerAgent runs → returns session_id + questions
  POST /api/architect/{id}/complete  → user answers submitted → AutoTailorAgent runs → tailored resume

Both calls are Pro-tier only.
"""

import uuid
import logging
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import get_current_user
from backend.database import get_db
from backend.db_models import ArchitectSession, Job, User, UserTier
from backend.services.agent_gap_analyzer import GapAnalyzerAgent
from backend.services.agent_tailor import AutoTailorAgent
from backend.services.agent_orchestrator import AgentOrchestrator
from backend.services.agent_telemetry import AgentTelemetry

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/architect", tags=["Resume Architect"])


# ============================================================================
# Pydantic models
# ============================================================================

class ArchitectStartRequest(BaseModel):
    job_id: str
    resume_text: str = Field(..., min_length=100)


class ArchitectQuestion(BaseModel):
    id: str
    gap: str
    question: str


class ArchitectStartResponse(BaseModel):
    session_id: str
    gaps: dict
    questions: List[ArchitectQuestion]
    status: str


class ArchitectCompleteRequest(BaseModel):
    answers: Dict[str, str]  # {question_id: user_answer}


class ArchitectCompleteResponse(BaseModel):
    session_id: str
    tailored_resume: str
    match_score: Optional[float]
    match_tier: Optional[str]
    missing_signals: Optional[list]
    status: str


# ============================================================================
# Helpers
# ============================================================================

def _pro_check(user: User):
    if user.tier not in (UserTier.pro, UserTier.agency):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Resume Architect requires a Pro subscription.",
        )


# ============================================================================
# Phase 1: Start session – gap analysis + questions
# ============================================================================

@router.post("/start", response_model=ArchitectStartResponse, status_code=201)
async def start_architect_session(
    body: ArchitectStartRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Analyze gaps between the user's resume and the target job,
    then return targeted questions to fill those gaps.
    """
    _pro_check(current_user)

    # Verify job exists
    stmt = select(Job).where(Job.id == uuid.UUID(body.job_id))
    res = await db.execute(stmt)
    job = res.scalar_one_or_none()
    if not job:
        raise HTTPException(404, "Job not found")

    telemetry = AgentTelemetry(db)
    gap_agent = GapAnalyzerAgent(
        user_id=str(current_user.id),
        telemetry_tracker=telemetry,
    )

    # Run gap_detector + question_generator tools directly (no orchestrator needed here)
    gaps = await gap_agent._gap_detector(
        resume_text=body.resume_text,
        job_description=job.description,
    )
    questions = await gap_agent._question_generator(
        gaps=gaps,
        job_description=job.description,
    )

    # Persist session
    session = ArchitectSession(
        user_id=current_user.id,
        job_id=job.id,
        base_resume=body.resume_text,
        gaps=gaps,
        questions=questions,
        status="awaiting_input",
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    return ArchitectStartResponse(
        session_id=str(session.id),
        gaps=gaps,
        questions=[
            ArchitectQuestion(
                id=q.get("id", f"q{i}"),
                gap=q.get("gap", ""),
                question=q.get("question", ""),
            )
            for i, q in enumerate(questions)
        ],
        status="awaiting_input",
    )


# ============================================================================
# Phase 2: Complete session – tailor with user answers
# ============================================================================

@router.post("/{session_id}/complete", response_model=ArchitectCompleteResponse)
async def complete_architect_session(
    session_id: str,
    body: ArchitectCompleteRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Submit answers to gap questions, then run AutoTailorAgent to produce
    the final tailored resume enriched with the user's context.
    """
    _pro_check(current_user)

    stmt = select(ArchitectSession).where(
        ArchitectSession.id == uuid.UUID(session_id),
        ArchitectSession.user_id == current_user.id,
    )
    res = await db.execute(stmt)
    session = res.scalar_one_or_none()
    if not session:
        raise HTTPException(404, "Architect session not found")
    if session.status == "complete":
        return ArchitectCompleteResponse(
            session_id=session_id,
            tailored_resume=session.tailored_resume or "",
            match_score=None,
            match_tier=None,
            missing_signals=None,
            status="complete",
        )

    # Get job
    job_stmt = select(Job).where(Job.id == session.job_id)
    job_res = await db.execute(job_stmt)
    job = job_res.scalar_one_or_none()
    if not job:
        raise HTTPException(404, "Associated job not found")

    # Build enriched resume text by appending answers as addendum
    extra_lines = []
    for q in (session.questions or []):
        qid = q.get("id", "")
        answer = body.answers.get(qid, "")
        if answer:
            extra_lines.append(f"Additional context – {q.get('gap', '')}: {answer}")
    addendum = "\n".join(extra_lines)
    enriched_resume = session.base_resume
    if addendum:
        enriched_resume = f"{session.base_resume}\n\n--- Additional Context ---\n{addendum}"

    # Run AutoTailorAgent
    telemetry = AgentTelemetry(db)
    tailor_agent = AutoTailorAgent(
        user_id=str(current_user.id),
        telemetry_tracker=telemetry,
    )
    tailor_result = await tailor_agent.execute(
        "rewrite_resume_for_job",
        {"resume_text": enriched_resume, "jd_text": job.description},
    )

    tailored_text = (
        tailor_result.get("rewritten_resume", enriched_resume)
        if isinstance(tailor_result, dict)
        else enriched_resume
    )

    # Quick match score
    match_score = None
    match_tier = None
    missing_signals = None
    try:
        from backend.services.matcher_service import get_matcher
        import asyncio

        matcher = get_matcher()
        metrics = await asyncio.to_thread(
            matcher.compute_match_metrics,
            job.description,
            tailored_text,
            None,
        )
        match_score = getattr(metrics, "semantic_similarity", None)
        match_tier = getattr(metrics, "match_tier", None)
        missing_signals = getattr(metrics, "missing_signals", None)
    except Exception as score_err:
        logger.warning(f"[Architect] Scoring failed: {score_err}")

    # Update session
    session.user_answers = body.answers
    session.tailored_resume = tailored_text
    session.status = "complete"
    await db.commit()

    return ArchitectCompleteResponse(
        session_id=session_id,
        tailored_resume=tailored_text,
        match_score=match_score,
        match_tier=match_tier,
        missing_signals=missing_signals,
        status="complete",
    )

"""
Master Orchestrator API Routes

Endpoints:
  POST /api/orchestrator/plan      — Decompose goal into action plan
  POST /api/orchestrator/execute   — Execute full orchestrated workflow
  POST /api/orchestrator/feedback  — Submit feedback on a plan step
  POST /api/orchestrator/outcome   — Report application outcome (closed-loop)
  GET  /api/orchestrator/journey/{session_id} — Retrieve journey details
"""

import uuid
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import get_current_user
from backend.database import get_db
from backend.db_models import User
from backend.services.master_orchestrator import MasterOrchestrator
from backend.services.agent_telemetry import AgentTelemetry

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/orchestrator", tags=["Master Orchestrator"])


# ========================================================================
# Request / Response Models
# ========================================================================

class PlanRequest(BaseModel):
    resume_text: str = Field(..., min_length=50, max_length=50000)
    job_description: str = Field(..., min_length=20, max_length=30000)
    user_profile: Optional[Dict[str, Any]] = None
    job_search_history: Optional[List[Dict]] = None


class ExecuteRequest(BaseModel):
    resume_text: str = Field(..., min_length=50, max_length=50000)
    job_description: str = Field(..., min_length=20, max_length=30000)
    user_preferences: Optional[Dict[str, Any]] = None


class FeedbackRequest(BaseModel):
    session_id: str
    step_id: str
    user_action: str = Field(..., pattern="^(accepted|edited|rejected)$")
    rating: Optional[int] = Field(None, ge=1, le=5)
    edited_output: Optional[Dict[str, Any]] = None


class OutcomeRequest(BaseModel):
    journey_session_id: Optional[str] = None
    job_id: Optional[str] = None
    job_title: Optional[str] = None
    company_name: Optional[str] = None
    outcome: str = Field(
        ..., pattern="^(applied|interview|offer|hired|rejected|ghosted|abandoned)$"
    )
    outcome_details: Optional[Dict[str, Any]] = None
    user_satisfaction: Optional[int] = Field(None, ge=1, le=5)
    user_notes: Optional[str] = None


# ========================================================================
# POST /api/orchestrator/plan
# ========================================================================

@router.post("/plan")
async def create_plan(
    request: PlanRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Decompose a job application goal into a multi-step action plan.
    Returns the plan without executing it.
    """
    try:
        telemetry = AgentTelemetry(db)
        within_budget, remaining = await telemetry.check_monthly_budget(str(current_user.id))
        if not within_budget:
            raise HTTPException(
                status_code=402,
                detail=f"Monthly AI budget exceeded. Remaining: ${remaining / 100:.2f}.",
            )

        orchestrator = MasterOrchestrator(
            user_id=str(current_user.id),
            user_tier=current_user.tier.value if current_user.tier else "free",
            db=db,
        )

        plan = await orchestrator.decompose_goal(
            resume_text=request.resume_text,
            job_description=request.job_description,
            user_profile=request.user_profile,
            job_search_history=request.job_search_history,
        )

        return {
            "session_id": orchestrator.session_id,
            "steps": [s.to_dict() for s in plan],
            "total_steps": len(plan),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[ORCHESTRATOR] Plan error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========================================================================
# POST /api/orchestrator/execute
# ========================================================================

@router.post("/execute")
async def execute_plan(
    request: ExecuteRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Run the full orchestrated workflow: decompose + execute all steps.
    Returns completed results, premium teasers, and next actions.
    """
    try:
        telemetry = AgentTelemetry(db)
        within_budget, remaining = await telemetry.check_monthly_budget(str(current_user.id))
        if not within_budget:
            raise HTTPException(
                status_code=402,
                detail=f"Monthly AI budget exceeded. Remaining: ${remaining / 100:.2f}.",
            )

        orchestrator = MasterOrchestrator(
            user_id=str(current_user.id),
            user_tier=current_user.tier.value if current_user.tier else "free",
            db=db,
        )

        # Step 1: Decompose
        await orchestrator.decompose_goal(
            resume_text=request.resume_text,
            job_description=request.job_description,
        )

        # Step 2: Execute
        result = await orchestrator.execute_plan(
            resume_text=request.resume_text,
            job_description=request.job_description,
            user_preferences=request.user_preferences,
        )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[ORCHESTRATOR] Execute error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========================================================================
# POST /api/orchestrator/feedback
# ========================================================================

@router.post("/feedback")
async def submit_feedback(
    request: FeedbackRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Submit feedback on a specific plan step.
    Used for both real-time plan adaptation and DPO training data.
    """
    # We need to reconstruct the orchestrator from the session.
    # In production, this would load from a session store (Redis).
    # For now, log directly to the training pipeline.
    from backend.services.agent_training import AgentTrainingPipeline

    try:
        pipeline = AgentTrainingPipeline(db)
        await pipeline.log_agent_interaction(
            agent_type=f"orchestrator",
            user_id=str(current_user.id),
            job_id=None,
            input_context={"session_id": request.session_id, "step_id": request.step_id},
            agent_output={},
            user_action=request.user_action,
            user_edited_output=request.edited_output,
            rating=request.rating,
        )

        return {"status": "feedback_recorded", "session_id": request.session_id}

    except Exception as e:
        logger.error(f"[ORCHESTRATOR] Feedback error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========================================================================
# POST /api/orchestrator/outcome
# ========================================================================

@router.post("/outcome")
async def report_outcome(
    request: OutcomeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Report a real-world outcome: applied, interview, offer, hired, rejected, etc.
    This is the critical closed-loop signal for reward model training.
    """
    try:
        outcome_id = str(uuid.uuid4())

        # Find the associated journey if session_id provided
        journey_id = None
        if request.journey_session_id:
            result = await db.execute(
                text("SELECT id FROM user_journeys WHERE session_id = :sid AND user_id = :uid"),
                {"sid": request.journey_session_id, "uid": str(current_user.id)},
            )
            row = result.first()
            if row:
                journey_id = str(row[0])

        await db.execute(
            text("""
                INSERT INTO job_application_outcomes (
                    id, user_id, journey_id, job_id,
                    job_title, company_name, outcome, outcome_details,
                    user_satisfaction, user_notes, outcome_reported_at
                ) VALUES (
                    :id, :user_id, :journey_id, :job_id,
                    :job_title, :company_name, :outcome, :outcome_details,
                    :user_satisfaction, :user_notes, NOW()
                )
            """),
            {
                "id": outcome_id,
                "user_id": str(current_user.id),
                "journey_id": journey_id,
                "job_id": request.job_id,
                "job_title": request.job_title,
                "company_name": request.company_name,
                "outcome": request.outcome,
                "outcome_details": (
                    __import__("json").dumps(request.outcome_details)
                    if request.outcome_details
                    else None
                ),
                "user_satisfaction": request.user_satisfaction,
                "user_notes": request.user_notes,
            },
        )
        await db.commit()

        # If positive outcome, update journey DPO label
        if journey_id and request.outcome in ("interview", "offer", "hired"):
            await db.execute(
                text("UPDATE user_journeys SET dpo_label = 'chosen' WHERE id = :jid"),
                {"jid": journey_id},
            )
            await db.commit()

        # Send congratulatory message with value reinforcement
        congrats = None
        if request.outcome in ("interview", "offer", "hired"):
            congrats = _build_congrats_message(request.outcome, current_user.tier.value)

        return {
            "status": "outcome_recorded",
            "outcome_id": outcome_id,
            "journey_linked": journey_id is not None,
            "congratulations": congrats,
        }

    except Exception as e:
        logger.error(f"[ORCHESTRATOR] Outcome error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========================================================================
# GET /api/orchestrator/journey/{session_id}
# ========================================================================

@router.get("/journey/{session_id}")
async def get_journey(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve a journey and its outcomes by session ID."""
    result = await db.execute(
        text("""
            SELECT
                uj.*,
                COALESCE(
                    json_agg(
                        json_build_object(
                            'outcome', jao.outcome,
                            'job_title', jao.job_title,
                            'company_name', jao.company_name,
                            'outcome_reported_at', jao.outcome_reported_at
                        )
                    ) FILTER (WHERE jao.id IS NOT NULL),
                    '[]'
                ) AS outcomes
            FROM user_journeys uj
            LEFT JOIN job_application_outcomes jao ON jao.journey_id = uj.id
            WHERE uj.session_id = :sid AND uj.user_id = :uid
            GROUP BY uj.id
        """),
        {"sid": session_id, "uid": str(current_user.id)},
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Journey not found")

    return dict(row._mapping)


# ========================================================================
# Helpers
# ========================================================================

def _build_congrats_message(outcome: str, user_tier: str) -> Dict:
    """Build a congratulatory message that reinforces AI value."""
    messages = {
        "interview": {
            "headline": "Interview Secured! Your preparation is paying off.",
            "body": (
                "Our AI identified the key skills this role demands and optimized "
                "your resume to highlight them. Interview-prepped candidates using "
                "our platform report 2x higher confidence going in."
            ),
            "cta": (
                "Upgrade to Pro for company-specific interview questions and "
                "salary negotiation scripts."
                if user_tier == "free"
                else "Use Interview Prep to practice with role-specific questions."
            ),
        },
        "offer": {
            "headline": "Congratulations on your offer!",
            "body": (
                "From resume optimization to interview preparation, "
                "your AI-powered job search strategy delivered results. "
                "Users who complete our full workflow see 40% faster time-to-offer."
            ),
            "cta": (
                "Upgrade to Pro for salary negotiation assistance."
                if user_tier == "free"
                else "Need help evaluating or negotiating? Your AI coach is ready."
            ),
        },
        "hired": {
            "headline": "You're hired! We're thrilled for you.",
            "body": (
                "Your journey from first scan to signed offer is exactly what "
                "our AI was built to support. Thank you for trusting us with "
                "this important milestone."
            ),
            "cta": "Share your success story and help others land their dream job!",
        },
    }
    return messages.get(outcome, {"headline": "Great news!", "body": "", "cta": ""})

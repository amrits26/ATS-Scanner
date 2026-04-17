"""
Training API Routes — Log interactions, retrieve metrics, export data.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import get_current_user
from backend.database import get_db
from backend.db_models import User
from backend.services.agent_training import AgentTrainingPipeline

router = APIRouter(prefix="/api/training", tags=["training"])


# ------------------------------------------------------------------
# Request / Response schemas
# ------------------------------------------------------------------

class LogInteractionRequest(BaseModel):
    agent_type: str
    job_id: Optional[str] = None
    input_context: dict
    agent_output: dict
    user_action: str = Field(..., pattern="^(accepted|edited|rejected|applied)$")
    user_edited_output: Optional[dict] = None
    rating: Optional[int] = Field(None, ge=1, le=5)


class TrainingMetricsResponse(BaseModel):
    agent_type: str
    total_interactions: int
    acceptance_rate: float
    average_rating: float
    average_edit_distance: float
    period_days: int


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------

@router.post("/log")
async def log_agent_interaction(
    request: LogInteractionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Log a user interaction with an agent output for training."""
    pipeline = AgentTrainingPipeline(db)
    entry = await pipeline.log_agent_interaction(
        agent_type=request.agent_type,
        user_id=str(current_user.id),
        job_id=request.job_id,
        input_context=request.input_context,
        agent_output=request.agent_output,
        user_action=request.user_action,
        user_edited_output=request.user_edited_output,
        rating=request.rating,
    )
    return {"id": str(entry.id), "status": "logged"}


@router.get("/metrics/{agent_type}", response_model=TrainingMetricsResponse)
async def get_agent_metrics(
    agent_type: str,
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get performance metrics for a specific agent type."""
    pipeline = AgentTrainingPipeline(db)
    metrics = await pipeline.get_agent_performance_metrics(agent_type, days)
    return {"agent_type": agent_type, **metrics}


@router.get("/export/{agent_type}")
async def export_training_data(
    agent_type: str,
    min_rating: int = Query(4, ge=1, le=5),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Export high-quality training examples (pro users only)."""
    if current_user.tier.value not in ("pro", "agency"):
        raise HTTPException(403, "Pro or Agency tier required")

    pipeline = AgentTrainingPipeline(db)
    data = await pipeline.export_training_data(agent_type, min_rating)
    return {"count": len(data), "data": data}


@router.post("/generate-synthetic/{agent_type}")
async def generate_synthetic_examples(
    agent_type: str,
    job_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Manually trigger synthetic example generation (pro users only)."""
    if current_user.tier.value not in ("pro", "agency"):
        raise HTTPException(403, "Pro or Agency tier required")

    pipeline = AgentTrainingPipeline(db)
    await pipeline.generate_synthetic_examples(agent_type, job_id)
    return {"status": "synthetic examples generated"}

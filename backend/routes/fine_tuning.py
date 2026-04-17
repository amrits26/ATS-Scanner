"""
Fine-Tuning Pipeline API Routes

Admin-only endpoints for managing fine-tuning jobs and model deployments.
Admin = user whose email matches ADMIN_EMAIL env var.
"""

import os
import logging
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import get_current_user
from backend.database import get_db
from backend.db_models import (
    AgentFeedbackLog,
    FineTuningJob,
    ModelDeployment,
    User,
)
from backend.services.fine_tuning import FineTuningService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/fine-tuning", tags=["fine-tuning"])

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "demo@intelliresume.ai")


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _require_admin(user: User):
    """Raise 403 if the user is not the admin."""
    if not user or user.email != ADMIN_EMAIL:
        raise HTTPException(403, "Fine-tuning management requires admin access")


# ------------------------------------------------------------------
# Request / Response schemas
# ------------------------------------------------------------------

class StartFineTuningRequest(BaseModel):
    agent_type: str
    provider: str = "together"
    base_model: str = "meta-llama/Llama-3.2-3B-Instruct"
    hyperparameters: Optional[dict] = None


class FineTuningJobResponse(BaseModel):
    id: str
    agent_type: str
    provider: str
    base_model: str
    status: str
    examples_count: int
    fine_tuned_model_id: Optional[str] = None
    error_message: Optional[str] = None
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    cost_usd: Optional[float] = None
    is_active: bool = False


class DeploymentResponse(BaseModel):
    id: str
    agent_type: str
    model_id: str
    provider: str
    is_active: bool
    rollout_percentage: int = 100
    deployed_at: str
    performance_metrics: Optional[dict] = None


def _job_to_dict(job: FineTuningJob) -> dict:
    return {
        "id": str(job.id),
        "agent_type": job.agent_type,
        "provider": job.provider,
        "base_model": job.base_model,
        "status": job.status,
        "examples_count": job.examples_count or 0,
        "fine_tuned_model_id": job.fine_tuned_model_id,
        "error_message": job.error_message,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "cost_usd": job.cost_usd,
        "is_active": bool(job.is_active),
    }


def _deployment_to_dict(d: ModelDeployment) -> dict:
    return {
        "id": str(d.id),
        "agent_type": d.agent_type,
        "model_id": d.model_id,
        "provider": d.provider,
        "is_active": d.is_active,
        "rollout_percentage": d.rollout_percentage if d.rollout_percentage is not None else 100,
        "deployed_at": d.deployed_at.isoformat() if d.deployed_at else None,
        "performance_metrics": d.performance_metrics,
    }


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------

@router.post("/start", response_model=FineTuningJobResponse)
async def start_fine_tuning(
    request: StartFineTuningRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Start a new fine-tuning job (admin only)."""
    _require_admin(current_user)

    service = FineTuningService(db)
    job = await service.start_fine_tuning_job(
        agent_type=request.agent_type,
        provider=request.provider,
        base_model=request.base_model,
        hyperparameters=request.hyperparameters,
        created_by=current_user.id,
    )
    return _job_to_dict(job)


@router.get("/jobs", response_model=List[FineTuningJobResponse])
async def list_fine_tuning_jobs(
    agent_type: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all fine-tuning jobs (admin only)."""
    _require_admin(current_user)

    service = FineTuningService(db)
    jobs = await service.list_fine_tuning_jobs(agent_type)
    return [_job_to_dict(j) for j in jobs]


@router.get("/jobs/{job_id}", response_model=FineTuningJobResponse)
async def get_fine_tuning_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific fine-tuning job."""
    _require_admin(current_user)

    stmt = select(FineTuningJob).where(FineTuningJob.id == job_id)
    result = await db.execute(stmt)
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(404, "Job not found")
    return _job_to_dict(job)


@router.post("/jobs/{job_id}/poll", response_model=FineTuningJobResponse)
async def poll_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Poll the provider for an in-progress job's latest status."""
    _require_admin(current_user)

    service = FineTuningService(db)
    job = await service.poll_job_status(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return _job_to_dict(job)


@router.post("/deploy/{job_id}")
async def deploy_model(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Manually deploy a completed fine-tuned model."""
    _require_admin(current_user)

    stmt = select(FineTuningJob).where(FineTuningJob.id == job_id)
    result = await db.execute(stmt)
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(404, "Job not found")

    service = FineTuningService(db)
    try:
        await service.deploy_model_manually(job)
    except ValueError as e:
        raise HTTPException(400, str(e))

    return {"status": "deployed", "model_id": job.fine_tuned_model_id}


@router.get("/deployments", response_model=List[DeploymentResponse])
async def list_deployments(
    agent_type: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List model deployments."""
    _require_admin(current_user)

    query = select(ModelDeployment).order_by(ModelDeployment.deployed_at.desc())
    if agent_type:
        query = query.where(ModelDeployment.agent_type == agent_type)
    result = await db.execute(query)
    deployments = result.scalars().all()
    return [_deployment_to_dict(d) for d in deployments]


@router.get("/check-readiness/{agent_type}")
async def check_readiness(
    agent_type: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Check if enough examples exist to trigger fine-tuning for an agent type."""
    _require_admin(current_user)

    service = FineTuningService(db)
    info = await service.should_trigger_fine_tuning(agent_type)
    return {"agent_type": agent_type, **info}


@router.post("/evaluate/{deployment_id}")
async def evaluate_deployment(
    deployment_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Evaluate a deployed model's performance over the last 30 days."""
    _require_admin(current_user)

    service = FineTuningService(db)
    try:
        metrics = await service.evaluate_model_performance(deployment_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return metrics


class UpdateRolloutRequest(BaseModel):
    rollout_percentage: int  # 1-100


@router.patch("/deployments/{deployment_id}/rollout")
async def update_rollout(
    deployment_id: str,
    request: UpdateRolloutRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update the rollout percentage for a deployment (A/B testing)."""
    _require_admin(current_user)

    if not 1 <= request.rollout_percentage <= 100:
        raise HTTPException(400, "rollout_percentage must be between 1 and 100")

    stmt = select(ModelDeployment).where(ModelDeployment.id == deployment_id)
    result = await db.execute(stmt)
    deployment = result.scalar_one_or_none()
    if not deployment:
        raise HTTPException(404, "Deployment not found")

    deployment.rollout_percentage = request.rollout_percentage
    await db.commit()
    return _deployment_to_dict(deployment)

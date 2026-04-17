"""
Job Agent Routes – Saved job-search automation (Pro tier only).

Endpoints:
  POST   /api/job-agents/           Create a new agent
  GET    /api/job-agents/           List user's agents
  DELETE /api/job-agents/{id}       Deactivate (soft-delete)
  POST   /api/job-agents/{id}/run   Enqueue an immediate scrape
"""

import uuid
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import get_current_user, require_pro
from backend.database import get_db
from backend.db_models import JobAgent, JobAgentResult, Job, User, UserTier

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/job-agents", tags=["Job Agents"])


# ============================================================================
# Pydantic models
# ============================================================================

class JobAgentCreate(BaseModel):
    name: str = Field(..., max_length=255)
    query: str = Field(..., max_length=500)
    location: Optional[str] = Field(None, max_length=255)
    country_code: str = Field("US", max_length=2)
    visa_sponsorship: bool = False
    remote_only: bool = False
    salary_min: Optional[int] = None
    base_resume_text: Optional[str] = None
    email_digest_enabled: bool = True
    frequency: str = Field("daily", pattern="^(daily|weekly)$")


class JobAgentResponse(BaseModel):
    id: str
    name: str
    query: str
    location: Optional[str]
    country_code: str
    visa_sponsorship: bool
    remote_only: bool
    salary_min: Optional[int]
    email_digest_enabled: bool
    frequency: str
    is_active: bool
    last_run_at: Optional[str]
    created_at: str
    result_count: int = 0

    class Config:
        from_attributes = True


class JobAgentResultResponse(BaseModel):
    id: str
    job_id: str
    job_title: Optional[str]
    company: Optional[str]
    location: Optional[str]
    match_score: Optional[float]
    match_tier: Optional[str]
    missing_signals: Optional[list]
    was_emailed: bool
    created_at: str


# ============================================================================
# Helpers
# ============================================================================

def _pro_check(user: User):
    if user.tier not in (UserTier.pro, UserTier.agency):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Job Agents require a Pro subscription.",
        )


# ============================================================================
# Endpoints
# ============================================================================

@router.post("/", response_model=JobAgentResponse, status_code=201)
async def create_job_agent(
    body: JobAgentCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new saved job-search agent (Pro only)."""
    _pro_check(current_user)

    agent = JobAgent(
        user_id=current_user.id,
        name=body.name,
        query=body.query,
        location=body.location,
        country_code=body.country_code.upper(),
        visa_sponsorship=body.visa_sponsorship,
        remote_only=body.remote_only,
        salary_min=body.salary_min,
        base_resume_text=body.base_resume_text,
        email_digest_enabled=body.email_digest_enabled,
        frequency=body.frequency,
    )
    db.add(agent)
    await db.commit()
    await db.refresh(agent)

    return JobAgentResponse(
        id=str(agent.id),
        name=agent.name,
        query=agent.query,
        location=agent.location,
        country_code=agent.country_code,
        visa_sponsorship=agent.visa_sponsorship,
        remote_only=agent.remote_only,
        salary_min=agent.salary_min,
        email_digest_enabled=agent.email_digest_enabled,
        frequency=agent.frequency,
        is_active=agent.is_active,
        last_run_at=agent.last_run_at.isoformat() if agent.last_run_at else None,
        created_at=agent.created_at.isoformat(),
    )


@router.get("/", response_model=List[JobAgentResponse])
async def list_job_agents(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all active agents for the current user."""
    _pro_check(current_user)

    stmt = (
        select(JobAgent)
        .where(JobAgent.user_id == current_user.id, JobAgent.is_active == True)
        .order_by(JobAgent.created_at.desc())
    )
    result = await db.execute(stmt)
    agents = result.scalars().all()

    out = []
    for a in agents:
        # Count results
        count_stmt = select(JobAgentResult).where(JobAgentResult.job_agent_id == a.id)
        res = await db.execute(count_stmt)
        cnt = len(res.scalars().all())

        out.append(
            JobAgentResponse(
                id=str(a.id),
                name=a.name,
                query=a.query,
                location=a.location,
                country_code=a.country_code,
                visa_sponsorship=a.visa_sponsorship,
                remote_only=a.remote_only,
                salary_min=a.salary_min,
                email_digest_enabled=a.email_digest_enabled,
                frequency=a.frequency,
                is_active=a.is_active,
                last_run_at=a.last_run_at.isoformat() if a.last_run_at else None,
                created_at=a.created_at.isoformat(),
                result_count=cnt,
            )
        )
    return out


@router.get("/{agent_id}/results", response_model=List[JobAgentResultResponse])
async def get_agent_results(
    agent_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the latest discovered jobs for a specific agent."""
    _pro_check(current_user)

    # Verify ownership
    agent_stmt = select(JobAgent).where(
        JobAgent.id == uuid.UUID(agent_id),
        JobAgent.user_id == current_user.id,
    )
    agent_res = await db.execute(agent_stmt)
    agent = agent_res.scalar_one_or_none()
    if not agent:
        raise HTTPException(404, "Agent not found")

    stmt = (
        select(JobAgentResult, Job)
        .join(Job, JobAgentResult.job_id == Job.id)
        .where(JobAgentResult.job_agent_id == agent.id)
        .order_by(JobAgentResult.created_at.desc())
        .limit(50)
    )
    rows = await db.execute(stmt)

    out = []
    for jar, job in rows:
        out.append(
            JobAgentResultResponse(
                id=str(jar.id),
                job_id=str(jar.job_id),
                job_title=job.title if job else None,
                company=job.company if job else None,
                location=job.location if job else None,
                match_score=jar.match_score,
                match_tier=jar.match_tier,
                missing_signals=jar.missing_signals,
                was_emailed=jar.was_emailed,
                created_at=jar.created_at.isoformat(),
            )
        )
    return out


@router.delete("/{agent_id}", status_code=204)
async def deactivate_job_agent(
    agent_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete (deactivate) a job agent."""
    _pro_check(current_user)

    stmt = select(JobAgent).where(
        JobAgent.id == uuid.UUID(agent_id),
        JobAgent.user_id == current_user.id,
    )
    result = await db.execute(stmt)
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(404, "Agent not found")

    agent.is_active = False
    await db.commit()


@router.post("/{agent_id}/run", status_code=202)
async def run_job_agent_now(
    agent_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Enqueue an immediate scrape run for this agent."""
    _pro_check(current_user)

    stmt = select(JobAgent).where(
        JobAgent.id == uuid.UUID(agent_id),
        JobAgent.user_id == current_user.id,
        JobAgent.is_active == True,
    )
    result = await db.execute(stmt)
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(404, "Agent not found or inactive")

    try:
        import arq
        import os

        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        redis = await arq.create_pool(arq.connections.RedisSettings.from_dsn(redis_url))
        await redis.enqueue_job("scrape_and_score_agent", str(agent.id))
        await redis.close()
        return {"queued": True, "agent_id": agent_id}
    except Exception as e:
        logger.warning(f"Could not enqueue job for agent {agent_id}: {e}")
        # Fall back: run synchronously in background
        from backend.jobs.background_jobs import BackgroundJobs
        import asyncio
        asyncio.create_task(BackgroundJobs.scrape_and_score_agent_by_id(str(agent.id)))
        return {"queued": False, "agent_id": agent_id, "fallback": "sync"}

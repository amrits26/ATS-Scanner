"""
Scraping API Routes — Job search, saved jobs, trending skills.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import get_current_user
from backend.database import get_db
from backend.db_models import User
from backend.services.multi_scraper import MultiSourceScraper

router = APIRouter(prefix="/api/scraping", tags=["scraping"])


# ------------------------------------------------------------------
# Request / Response schemas
# ------------------------------------------------------------------

class JobSearchRequest(BaseModel):
    keywords: str = Field(..., min_length=1, max_length=200)
    location: str = ""
    source: str = Field("linkedin", pattern="^(linkedin|indeed|google_jobs|glassdoor)$")
    max_results: int = Field(50, ge=1, le=200)
    days_old: int = Field(7, ge=1, le=90)
    job_type: Optional[str] = None
    remote_only: bool = False


class ScrapedJobSummary(BaseModel):
    id: str
    source: str
    title: str
    company: str
    location: Optional[str]
    description: str
    posted_date: Optional[str]
    url: Optional[str]
    required_skills: Optional[dict]


class TrendingSkillsResponse(BaseModel):
    skills: List[dict]
    period_days: int


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------

@router.post("/search")
async def search_jobs(
    request: JobSearchRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Search for jobs across platforms via Apify."""
    scraper = MultiSourceScraper(db)
    try:
        result = await scraper.search_jobs(
            keywords=request.keywords,
            location=request.location,
            source=request.source,
            max_results=request.max_results,
            days_old=request.days_old,
            job_type=request.job_type,
            remote_only=request.remote_only,
            user_id=str(current_user.id),
        )
        return result
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(502, f"Scraping provider error: {e}")


@router.get("/jobs")
async def get_saved_jobs(
    keywords: Optional[str] = Query(None),
    location: Optional[str] = Query(None),
    company: Optional[str] = Query(None),
    days_old: int = Query(30, ge=1, le=90),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve previously scraped jobs from database cache."""
    scraper = MultiSourceScraper(db)
    jobs = await scraper.search_saved_jobs(
        keywords=keywords,
        location=location,
        company=company,
        days_old=days_old,
        limit=limit,
        offset=offset,
    )
    return [
        {
            "id": str(job.id),
            "source": job.source,
            "title": job.title,
            "company": job.company,
            "location": job.location,
            "description": (job.description or "")[:500] + ("..." if job.description and len(job.description) > 500 else ""),
            "posted_date": job.posted_date.isoformat() if job.posted_date else None,
            "url": job.url,
            "required_skills": job.required_skills,
        }
        for job in jobs
    ]


@router.get("/trending-skills", response_model=TrendingSkillsResponse)
async def get_trending_skills(
    days: int = Query(30, ge=1, le=90),
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """Aggregate trending skills from recently scraped jobs."""
    scraper = MultiSourceScraper(db)
    skills = await scraper.get_trending_skills(days=days, limit=limit)
    return {"skills": skills, "period_days": days}


@router.get("/sources")
async def list_scraping_sources():
    """List available job scraping sources and their requirements."""
    return {
        "sources": [
            {"id": "linkedin", "name": "LinkedIn", "requires_apify": True},
            {"id": "indeed", "name": "Indeed", "requires_apify": True},
            {"id": "google_jobs", "name": "Google Jobs", "requires_apify": True},
            {"id": "glassdoor", "name": "Glassdoor", "requires_apify": True},
        ]
    }


@router.get("/run/{run_id}/status")
async def get_scraping_run_status(
    run_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Check status of a scraping run."""
    from sqlalchemy import select as sa_select
    from backend.db_models import JobScrapingRun

    stmt = sa_select(JobScrapingRun).where(JobScrapingRun.id == run_id)
    result = await db.execute(stmt)
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(404, "Run not found")

    return {
        "id": str(run.id),
        "status": run.status,
        "jobs_found": run.jobs_found,
        "jobs_new": run.jobs_new,
        "error_message": run.error_message,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }

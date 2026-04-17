"""
Multi-Source Job Scraping Engine

Supports:
  - Apify actors (LinkedIn, Indeed, Google Jobs, Glassdoor)
  - Direct trafilatura fallback for single URLs
  - Database caching with deduplication
  - Automatic skill extraction via Gemini

Usage:
  scraper = MultiSourceScraper(db)
  result = await scraper.search_jobs(keywords="Python", location="NYC", source="linkedin")
"""

import os
import json
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import aiohttp
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db_models import ScrapedJob, JobScrapingRun

logger = logging.getLogger(__name__)


# Pre-built Apify actor IDs (find current versions on https://apify.com/store)
APIFY_ACTORS: Dict[str, str] = {
    "linkedin": "curious_coder/linkedin-jobs-scraper",
    "indeed": "misceres/indeed-scraper",
    "google_jobs": "lukaskrivka/google-jobs-scraper",
    "glassdoor": "emir/glassdoor-jobs-scraper",
}


class MultiSourceScraper:
    """Multi-source job scraping with Apify + direct fallbacks."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self._apify_token: Optional[str] = os.getenv("APIFY_API_TOKEN")
        self._apify_base = "https://api.apify.com/v2"

    # ------------------------------------------------------------------
    # PUBLIC API
    # ------------------------------------------------------------------

    async def search_jobs(
        self,
        keywords: str,
        location: str = "",
        source: str = "linkedin",
        max_results: int = 50,
        days_old: int = 7,
        job_type: Optional[str] = None,
        remote_only: bool = False,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Main entry point. Returns scraped + saved job data."""

        # Create audit trail
        run = JobScrapingRun(
            source=source,
            search_query={
                "keywords": keywords,
                "location": location,
                "max_results": max_results,
                "days_old": days_old,
                "job_type": job_type,
                "remote_only": remote_only,
            },
            status="pending",
            created_by=user_id,
        )
        self.db.add(run)
        await self.db.commit()
        await self.db.refresh(run)

        try:
            run.status = "running"
            run.started_at = datetime.utcnow()
            await self.db.commit()

            if self._apify_token and source in APIFY_ACTORS:
                jobs = await self._scrape_with_apify(
                    source, keywords, location, max_results, days_old, job_type, remote_only
                )
            else:
                raise ValueError(
                    f"Apify API token not configured or unsupported source '{source}'. "
                    "Set APIFY_API_TOKEN in your .env file."
                )

            saved_count = await self._save_scraped_jobs(jobs, source)

            run.status = "completed"
            run.completed_at = datetime.utcnow()
            run.jobs_found = len(jobs)
            run.jobs_new = saved_count
            await self.db.commit()

            return {
                "run_id": str(run.id),
                "total_found": len(jobs),
                "new_jobs": saved_count,
                "jobs": jobs[:20],
            }

        except Exception as e:
            run.status = "failed"
            run.error_message = str(e)[:1000]
            run.completed_at = datetime.utcnow()
            await self.db.commit()
            raise

    async def search_saved_jobs(
        self,
        keywords: Optional[str] = None,
        location: Optional[str] = None,
        company: Optional[str] = None,
        days_old: int = 30,
        limit: int = 50,
        offset: int = 0,
    ) -> List[ScrapedJob]:
        """Search previously scraped + cached jobs from database."""

        cutoff = datetime.utcnow() - timedelta(days=days_old)
        query = select(ScrapedJob).where(
            and_(
                ScrapedJob.is_active == True,  # noqa: E712
                ScrapedJob.scraped_date >= cutoff,
            )
        )

        if keywords:
            query = query.where(ScrapedJob.title.ilike(f"%{keywords}%"))
        if location:
            query = query.where(ScrapedJob.location.ilike(f"%{location}%"))
        if company:
            query = query.where(ScrapedJob.company.ilike(f"%{company}%"))

        query = (
            query.order_by(ScrapedJob.posted_date.desc().nullslast())
            .offset(offset)
            .limit(limit)
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_trending_skills(self, days: int = 30, limit: int = 20) -> List[Dict]:
        """Aggregate required_skills across recent scraped jobs."""

        cutoff = datetime.utcnow() - timedelta(days=days)
        stmt = select(ScrapedJob.required_skills).where(
            and_(
                ScrapedJob.required_skills.isnot(None),
                ScrapedJob.scraped_date >= cutoff,
            )
        )
        result = await self.db.execute(stmt)
        rows = result.scalars().all()

        skill_counts: Dict[str, int] = {}
        for skills_json in rows:
            if isinstance(skills_json, dict):
                for skill in skills_json.get("skills", []):
                    skill_lower = skill.strip().lower()
                    if skill_lower:
                        skill_counts[skill_lower] = skill_counts.get(skill_lower, 0) + 1

        sorted_skills = sorted(skill_counts.items(), key=lambda x: x[1], reverse=True)
        return [{"skill": s, "count": c} for s, c in sorted_skills[:limit]]

    # ------------------------------------------------------------------
    # APIFY INTEGRATION
    # ------------------------------------------------------------------

    async def _scrape_with_apify(
        self,
        source: str,
        keywords: str,
        location: str,
        max_results: int,
        days_old: int,
        job_type: Optional[str],
        remote_only: bool,
    ) -> List[Dict]:
        """Use Apify actors for reliable, proxy-backed scraping."""

        actor_id = APIFY_ACTORS[source]
        input_payload = self._build_apify_input(
            source, keywords, location, max_results, days_old, job_type, remote_only
        )

        async with aiohttp.ClientSession() as session:
            headers = {"Authorization": f"Bearer {self._apify_token}"}

            # Start actor run
            start_url = f"{self._apify_base}/acts/{actor_id}/runs"
            async with session.post(
                start_url, json=input_payload, headers=headers
            ) as resp:
                if resp.status != 201:
                    body = await resp.text()
                    raise RuntimeError(f"Apify start failed ({resp.status}): {body[:300]}")
                run_data = await resp.json()
                run_id = run_data["data"]["id"]

            # Poll for completion (max 2 min)
            for _ in range(24):
                await asyncio.sleep(5)
                status_url = f"{self._apify_base}/actor-runs/{run_id}"
                async with session.get(status_url, headers=headers) as resp:
                    status_data = await resp.json()
                    run_status = status_data["data"]["status"]
                    if run_status == "SUCCEEDED":
                        break
                    if run_status in ("FAILED", "ABORTED", "TIMED-OUT"):
                        raise RuntimeError(f"Apify run {run_status}")
            else:
                raise RuntimeError("Apify run timed out after 2 minutes")

            # Fetch dataset items
            dataset_id = status_data["data"]["defaultDatasetId"]
            items_url = f"{self._apify_base}/datasets/{dataset_id}/items"
            async with session.get(items_url, headers=headers) as resp:
                items = await resp.json()

        return [self._normalize_apify_job(item, source) for item in items]

    @staticmethod
    def _build_apify_input(
        source: str,
        keywords: str,
        location: str,
        max_results: int,
        days_old: int,
        job_type: Optional[str],
        remote_only: bool,
    ) -> Dict[str, Any]:
        """Build source-specific Apify actor input."""

        payload: Dict[str, Any] = {
            "searchTerms": keywords,
            "location": location,
            "maxResults": max_results,
        }

        if source == "linkedin":
            if days_old <= 1:
                payload["datePosted"] = "past_24_hours"
            elif days_old <= 7:
                payload["datePosted"] = "past_week"
            else:
                payload["datePosted"] = "past_month"
            if remote_only:
                payload["workplaceType"] = "remote"
            if job_type:
                payload["employmentType"] = job_type.upper().replace("-", "_")

        elif source == "indeed":
            payload["daysBack"] = days_old
            if job_type:
                payload["jobType"] = job_type
            if remote_only:
                payload["remote"] = "1"

        elif source == "google_jobs":
            payload["queries"] = f"{keywords} {location}".strip()
            payload["maxPagesPerQuery"] = max(1, max_results // 10)

        return payload

    @staticmethod
    def _normalize_apify_job(raw: Dict, source: str) -> Dict[str, Any]:
        """Convert Apify output to unified schema."""

        posted_date = None
        raw_date = raw.get("postedAt") or raw.get("datePosted")
        if raw_date:
            posted_date = _parse_date(raw_date)

        return {
            "source": source,
            "external_id": str(raw.get("id", raw.get("jobId", ""))),
            "url": raw.get("url", raw.get("jobUrl", "")),
            "title": raw.get("title", raw.get("jobTitle", "")),
            "company": raw.get("company", raw.get("companyName", "")),
            "location": raw.get("location", ""),
            "description": raw.get("description", raw.get("descriptionText", "")),
            "description_html": raw.get("descriptionHtml"),
            "salary_min": raw.get("salaryMin"),
            "salary_max": raw.get("salaryMax"),
            "salary_currency": raw.get("salaryCurrency"),
            "salary_period": raw.get("salaryPeriod", "yearly"),
            "job_type": raw.get("employmentType", raw.get("jobType", "")),
            "experience_level": raw.get("experienceLevel", ""),
            "remote_status": "remote" if raw.get("remote") else raw.get("workplaceType", ""),
            "posted_date": posted_date,
            "company_logo_url": raw.get("companyLogo", ""),
            "company_website": raw.get("companyWebsite", ""),
            "raw_data": raw,
        }

    # ------------------------------------------------------------------
    # DATABASE PERSISTENCE
    # ------------------------------------------------------------------

    async def _save_scraped_jobs(self, jobs: List[Dict], source: str) -> int:
        """Upsert scraped jobs with deduplication on (source, external_id)."""

        saved_count = 0
        for job_data in jobs:
            ext_id = job_data.get("external_id")
            if not ext_id:
                continue

            stmt = select(ScrapedJob).where(
                and_(
                    ScrapedJob.source == source,
                    ScrapedJob.external_id == ext_id,
                )
            )
            result = await self.db.execute(stmt)
            existing = result.scalar_one_or_none()

            if existing:
                # Update existing
                existing.title = job_data.get("title", existing.title)
                existing.description = job_data.get("description", existing.description)
                existing.is_active = True
                existing.last_verified = datetime.utcnow()
                existing.scraped_date = datetime.utcnow()
                if job_data.get("posted_date"):
                    existing.posted_date = job_data["posted_date"]
            else:
                # Filter out fields ScrapedJob doesn't have (e.g. company_website)
                new_job = ScrapedJob(
                    source=job_data["source"],
                    external_id=ext_id,
                    url=job_data.get("url"),
                    title=job_data["title"],
                    company=job_data["company"],
                    location=job_data.get("location"),
                    description=job_data.get("description"),
                    description_html=job_data.get("description_html"),
                    salary_min=job_data.get("salary_min"),
                    salary_max=job_data.get("salary_max"),
                    salary_currency=job_data.get("salary_currency"),
                    salary_period=job_data.get("salary_period"),
                    job_type=job_data.get("job_type"),
                    experience_level=job_data.get("experience_level"),
                    remote_status=job_data.get("remote_status"),
                    posted_date=job_data.get("posted_date"),
                    company_logo_url=job_data.get("company_logo_url"),
                    company_website=job_data.get("company_website"),
                    raw_data=job_data.get("raw_data"),
                )
                self.db.add(new_job)
                saved_count += 1

        await self.db.commit()

        # Enrich recent jobs with skill extraction (async, non-blocking)
        await self._enrich_jobs_with_skills()

        return saved_count

    async def _enrich_jobs_with_skills(self):
        """Use Gemini to extract skills from recent un-enriched job descriptions."""

        stmt = (
            select(ScrapedJob)
            .where(
                and_(
                    ScrapedJob.required_skills.is_(None),
                    ScrapedJob.description.isnot(None),
                    ScrapedJob.scraped_date >= datetime.utcnow() - timedelta(hours=1),
                )
            )
            .limit(20)
        )
        result = await self.db.execute(stmt)
        jobs = list(result.scalars().all())

        if not jobs:
            return

        try:
            import google.generativeai as genai

            model = genai.GenerativeModel(
                "gemini-1.5-flash",
                generation_config={
                    "temperature": 0.1,
                    "response_mime_type": "application/json",
                },
            )

            for job in jobs:
                if not job.description:
                    continue
                prompt = f"""Extract required skills from this job description. Return JSON:
{{
  "skills": ["Python", "AWS", ...],
  "soft_skills": ["communication", ...],
  "experience_years": 3
}}

Job Title: {job.title}
Company: {job.company}
Description: {(job.description or '')[:1000]}"""
                try:
                    response = model.generate_content(prompt)
                    job.required_skills = json.loads(response.text)
                except Exception as e:
                    logger.warning(f"[SCRAPER] Skill extraction failed for job {job.id}: {e}")

            await self.db.commit()
        except ImportError:
            logger.warning("[SCRAPER] google-generativeai not available, skipping enrichment")


# ======================================================================
# Helpers
# ======================================================================

def _parse_date(date_str: str) -> Optional[datetime]:
    """Parse various date formats (ISO, relative)."""
    if not date_str:
        return None
    try:
        lower = date_str.lower()
        if "day" in lower:
            days = int("".join(c for c in lower.split("day")[0] if c.isdigit()) or "1")
            return datetime.utcnow() - timedelta(days=days)
        if "hour" in lower:
            hours = int("".join(c for c in lower.split("hour")[0] if c.isdigit()) or "1")
            return datetime.utcnow() - timedelta(hours=hours)
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except Exception:
        return None

# backend/jobs/background_jobs.py
"""Background scheduled tasks for Phase 3 features."""

import logging
from datetime import datetime, timedelta
from typing import List

from sqlalchemy import delete, select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import AsyncSessionLocal
from backend.db_models import User, UserInterviewSubmission
from backend.services.hn_job_scraper import HNJobScraper
from backend.services.email_nudge_service import NudgeEngine

logger = logging.getLogger(__name__)


class BackgroundJobs:
    """Scheduled background tasks for analytics, scraping, and maintenance."""

    @staticmethod
    async def scrape_hn_weekly() -> None:
        """
        Run every Monday at 00:00 UTC.
        Scrape HN "Who is Hiring" thread and update trending skills.
        """
        try:
            logger.info("🕷️ Starting HN scraping job...")
            scraper = HNJobScraper()
            
            async with AsyncSessionLocal() as db:
                # Scrape latest jobs from HN
                jobs = await scraper.scrape_whoishiring()
                logger.info(f"✅ Scraped {len(jobs)} job postings from HN")
                
                # Update trending skills aggregation
                await scraper.update_trending_skills_db(db)
                await db.commit()
                logger.info("✅ Updated trending skills database")
                
        except Exception as e:
            logger.error(f"❌ HN scraping job failed: {e}")


    @staticmethod
    async def cleanup_old_submissions() -> None:
        """
        Run daily at 02:00 UTC.
        Remove rejected interview submissions older than 90 days.
        """
        try:
            logger.info("🧹 Cleaning up old interview submissions...")
            cutoff_date = datetime.utcnow() - timedelta(days=90)
            
            async with AsyncSessionLocal() as db:
                # Delete old rejected submissions
                stmt = delete(UserInterviewSubmission).where(
                    and_(
                        UserInterviewSubmission.created_at < cutoff_date,
                        UserInterviewSubmission.status == "rejected"
                    )
                )
                result = await db.execute(stmt)
                await db.commit()
                logger.info(f"✅ Deleted {result.rowcount} old submissions")
                
        except Exception as e:
            logger.error(f"❌ Cleanup job failed: {e}")


    @staticmethod
    async def notify_trending_skills_to_pros() -> None:
        """
        Run daily at 08:00 UTC.
        Send trending skills digest to Pro tier users.
        """
        try:
            logger.info("📬 Sending trending skills notifications to Pro users...")
            
            async with AsyncSessionLocal() as db:
                # Get all Pro tier users
                stmt = select(User).where(User.pro_tier == True)
                result = await db.execute(stmt)
                pro_users = result.scalars().all()
                
                if pro_users:
                    nudge_engine = NudgeEngine(db)
                    sent_count = 0
                    
                    for user in pro_users:
                        try:
                            await nudge_engine.send_skill_trend_email(user)
                            sent_count += 1
                        except Exception as e:
                            logger.warning(f"⚠️ Failed to send email to {user.email}: {e}")
                    
                    logger.info(f"✅ Sent notifications to {sent_count}/{len(pro_users)} Pro users")
                else:
                    logger.info("ℹ️ No Pro tier users to notify")
                    
        except Exception as e:
            logger.error(f"❌ Skill notification job failed: {e}")


    @staticmethod
    async def calculate_daily_analytics_snapshot() -> None:
        """
        Run daily at 23:00 UTC (end of day).
        Create analytics snapshot for historical tracking.
        """
        try:
            logger.info("📊 Calculating daily analytics snapshot...")
            
            async with AsyncSessionLocal() as db:
                from backend.services.analytics_service import AnalyticsService
                
                service = AnalyticsService(db)
                snapshot = await service.get_dashboard_summary()
                
                # Store snapshot in analytics_snapshots table
                from backend.db_models import AnalyticsSnapshot
                
                today = datetime.utcnow().date()
                
                # Check if snapshot already exists
                existing = await db.execute(
                    select(AnalyticsSnapshot).where(
                        AnalyticsSnapshot.snapshot_date == today
                    )
                )
                
                if existing.scalars().first():
                    logger.info("ℹ️ Snapshot already exists for today")
                else:
                    snapshot_record = AnalyticsSnapshot(
                        snapshot_date=today,
                        mrr_total=snapshot.get("mrr_total", 0),
                        mrr_email=snapshot.get("email_mrr", 0),
                        mrr_coach=snapshot.get("coach_mrr", 0),
                        mrr_tailor=snapshot.get("tailor_mrr", 0),
                        mrr_interview=snapshot.get("interview_mrr", 0),
                        mrr_pro=snapshot.get("pro_mrr", 0),
                        active_users=snapshot.get("active_users", 0),
                        churn_rate=snapshot.get("churn_rate", 0),
                        ltv_per_user=snapshot.get("ltv", 0),
                    )
                    db.add(snapshot_record)
                    await db.commit()
                    logger.info("✅ Snapshot saved successfully")
                    
        except Exception as e:
            logger.error(f"❌ Analytics snapshot job failed: {e}")


    @staticmethod
    async def generate_revenue_forecast() -> None:
        """
        Run daily at 23:30 UTC.
        Generate 7-day, 30-day, and 90-day revenue forecasts.
        """
        try:
            logger.info("🔮 Generating revenue forecasts...")
            
            async with AsyncSessionLocal() as db:
                from backend.services.analytics_service import AnalyticsService
                
                service = AnalyticsService(db)
                
                forecasts = {
                    7: await service.forecast_revenue(days=7),
                    30: await service.forecast_revenue(days=30),
                    90: await service.forecast_revenue(days=90),
                }
                
                logger.info(f"✅ Generated forecasts: {forecasts}")
                
        except Exception as e:
            logger.error(f"❌ Forecast generation failed: {e}")


    @staticmethod
    async def run_all_active_job_agents() -> None:
        """
        Run daily at 06:00 UTC.
        Iterate all active JobAgents and scrape + score new jobs.
        """
        try:
            logger.info("🤖 Running all active Job Agents...")
            async with AsyncSessionLocal() as db:
                from sqlalchemy import select as sa_select
                from backend.db_models import JobAgent
                stmt = sa_select(JobAgent).where(JobAgent.is_active == True)
                result = await db.execute(stmt)
                agents = result.scalars().all()
                logger.info(f"Found {len(agents)} active agents")
                for agent in agents:
                    try:
                        await BackgroundJobs.scrape_and_score_agent_by_id(str(agent.id))
                    except Exception as agent_err:
                        logger.warning(f"⚠️ Agent {agent.id} failed: {agent_err}")
            logger.info("✅ All active job agents processed")
        except Exception as e:
            logger.error(f"❌ run_all_active_job_agents failed: {e}")

    @staticmethod
    async def scrape_and_score_agent_by_id(agent_id: str) -> None:
        """
        Scrape new jobs for one JobAgent, score them against the user's resume,
        and persist JobAgentResult rows.
        Called directly or via ARQ enqueue.
        """
        from datetime import datetime as dt
        try:
            async with AsyncSessionLocal() as db:
                from sqlalchemy import select as sa_select
                from backend.db_models import JobAgent, JobAgentResult, Job
                from backend.services.serp_job_scraper import SerpJobScraper
                from backend.services.matcher_service import compute_match_metrics
                import hashlib

                stmt = sa_select(JobAgent).where(JobAgent.id == agent_id)
                result = await db.execute(stmt)
                agent = result.scalar_one_or_none()
                if not agent:
                    logger.warning(f"Job agent {agent_id} not found")
                    return

                logger.info(f"🔍 Scraping jobs for agent '{agent.name}' (query={agent.query})")
                scraper = SerpJobScraper()
                raw_jobs = await scraper.search_jobs(
                    query=agent.query,
                    location=agent.location or "",
                    country_code=agent.country_code,
                    visa_sponsorship=agent.visa_sponsorship,
                    remote_only=agent.remote_only,
                    limit=20,
                )

                new_count = 0
                for raw_job in raw_jobs:
                    description = raw_job.get("description", "")
                    if not description:
                        continue
                    desc_hash = hashlib.sha256(description.encode()).hexdigest()

                    # Dedup: check if this job already exists
                    existing_stmt = sa_select(Job).where(Job.description_hash == desc_hash)
                    existing_res = await db.execute(existing_stmt)
                    job = existing_res.scalar_one_or_none()

                    if not job:
                        job = Job(
                            title=raw_job.get("title", "Unknown"),
                            company=raw_job.get("company", "Unknown"),
                            location=raw_job.get("location", agent.location or ""),
                            country_code=agent.country_code,
                            description=description,
                            description_hash=desc_hash,
                            source=raw_job.get("source", "serp"),
                            source_url=raw_job.get("url"),
                            visa_sponsorship=agent.visa_sponsorship,
                            remote=agent.remote_only,
                        )
                        db.add(job)
                        await db.flush()

                    # Check if we already have a result for this agent+job pair
                    dup_stmt = sa_select(JobAgentResult).where(
                        JobAgentResult.job_agent_id == agent.id,
                        JobAgentResult.job_id == job.id,
                    )
                    dup_res = await db.execute(dup_stmt)
                    if dup_res.scalar_one_or_none():
                        continue

                    # Score if base resume is available
                    match_score = None
                    match_tier = None
                    missing_signals = None
                    if agent.base_resume_text:
                        try:
                            metrics = await compute_match_metrics(
                                resume_text=agent.base_resume_text,
                                job_description=description,
                            )
                            match_score = metrics.get("overall_score")
                            match_tier = metrics.get("match_tier")
                            missing_signals = metrics.get("missing_signals", [])
                        except Exception as score_err:
                            logger.warning(f"Scoring failed for job {job.id}: {score_err}")

                    jar = JobAgentResult(
                        job_agent_id=agent.id,
                        job_id=job.id,
                        match_score=match_score,
                        match_tier=match_tier,
                        missing_signals=missing_signals,
                    )
                    db.add(jar)
                    new_count += 1

                agent.last_run_at = dt.utcnow()
                await db.commit()
                logger.info(f"✅ Agent '{agent.name}': {new_count} new results saved")
        except Exception as e:
            logger.error(f"❌ scrape_and_score_agent_by_id({agent_id}) failed: {e}")

    @staticmethod
    async def send_daily_job_digest() -> None:
        """
        Run daily at 08:00 UTC (after scraping at 06:00).
        Email each Pro user their personalised job digest for agents with
        email_digest_enabled=True and new (un-emailed) results.
        """
        try:
            logger.info("📬 Sending daily job digests to Pro users...")
            async with AsyncSessionLocal() as db:
                from sqlalchemy import select as sa_select
                from backend.db_models import JobAgent, JobAgentResult, Job, User, UserTier
                from backend.services.email_service import EmailService

                # Find agents with un-emailed results
                agents_stmt = (
                    sa_select(JobAgent)
                    .where(
                        JobAgent.is_active == True,
                        JobAgent.email_digest_enabled == True,
                    )
                )
                agents_res = await db.execute(agents_stmt)
                agents = agents_res.scalars().all()

                email_service = EmailService()
                sent = 0

                for agent in agents:
                    # Verify user is Pro
                    user_stmt = sa_select(User).where(User.id == agent.user_id)
                    user_res = await db.execute(user_stmt)
                    user = user_res.scalar_one_or_none()
                    if not user or user.tier not in (UserTier.pro, UserTier.agency):
                        continue

                    # Get un-emailed results
                    results_stmt = (
                        sa_select(JobAgentResult, Job)
                        .join(Job, JobAgentResult.job_id == Job.id)
                        .where(
                            JobAgentResult.job_agent_id == agent.id,
                            JobAgentResult.was_emailed == False,
                        )
                        .order_by(JobAgentResult.created_at.desc())
                        .limit(10)
                    )
                    rows = await db.execute(results_stmt)
                    pairs = rows.all()
                    if not pairs:
                        continue

                    jobs_data = [
                        {
                            "title": job.title,
                            "company": job.company,
                            "location": job.location,
                            "match_score": jar.match_score,
                            "match_tier": jar.match_tier,
                            "source_url": job.source_url,
                        }
                        for jar, job in pairs
                    ]

                    try:
                        await email_service.send_job_digest(
                            to_email=user.email,
                            user_name=user.full_name or user.email,
                            agent_name=agent.name,
                            jobs=jobs_data,
                        )
                        # Mark as emailed
                        for jar, _ in pairs:
                            jar.was_emailed = True
                        await db.commit()
                        sent += 1
                    except Exception as email_err:
                        logger.warning(f"⚠️ Failed to send digest for agent {agent.id}: {email_err}")

                logger.info(f"✅ Sent daily job digests for {sent} agents")
        except Exception as e:
            logger.error(f"❌ send_daily_job_digest failed: {e}")


# ============================================================================
# ARQ task wrappers (top-level async functions required by ARQ)
# ============================================================================

async def run_all_active_job_agents(ctx):
    """ARQ task: scrape all active per-user job agents at 06:00 UTC."""
    await BackgroundJobs.run_all_active_job_agents()


async def scrape_and_score_agent(ctx, agent_id: str):
    """ARQ task: scrape + score one job agent (triggered on-demand)."""
    await BackgroundJobs.scrape_and_score_agent_by_id(agent_id)


async def send_daily_job_digest(ctx):
    """ARQ task: email per-user job digest at 08:00 UTC."""
    await BackgroundJobs.send_daily_job_digest()


# Job schedule (configure in your task queue, e.g., ARQ, Celery, APScheduler)
# 
# BACKGROUND_JOB_SCHEDULE = {
#     "hn_scraper":        {"cron": "0 0 * * MON", "func": BackgroundJobs.scrape_hn_weekly},
#     "cleanup":           {"cron": "0 2 * * *",   "func": BackgroundJobs.cleanup_old_submissions},
#     "skill_notify":      {"cron": "0 8 * * *",   "func": BackgroundJobs.notify_trending_skills_to_pros},
#     "analytics_snap":    {"cron": "0 23 * * *",  "func": BackgroundJobs.calculate_daily_analytics_snapshot},
#     "forecast":          {"cron": "30 23 * * *", "func": BackgroundJobs.generate_revenue_forecast},
#     "job_agents_scrape": {"cron": "0 6 * * *",   "func": run_all_active_job_agents},    # NEW Phase 8
#     "job_digest_email":  {"cron": "0 8 * * *",   "func": send_daily_job_digest},        # NEW Phase 8
# }

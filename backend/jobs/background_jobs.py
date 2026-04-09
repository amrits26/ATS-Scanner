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


# Job schedule (configure in your task queue, e.g., ARQ, Celery, APScheduler)
# 
# BACKGROUND_JOB_SCHEDULE = {
#     "hn_scraper": {"cron": "0 0 * * MON", "func": BackgroundJobs.scrape_hn_weekly},
#     "cleanup": {"cron": "0 2 * * *", "func": BackgroundJobs.cleanup_old_submissions},
#     "skill_notify": {"cron": "0 8 * * *", "func": BackgroundJobs.notify_trending_skills_to_pros},
#     "analytics_snap": {"cron": "0 23 * * *", "func": BackgroundJobs.calculate_daily_analytics_snapshot},
#     "forecast": {"cron": "30 23 * * *", "func": BackgroundJobs.generate_revenue_forecast},
# }

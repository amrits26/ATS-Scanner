"""
Fine-Tuning Scheduler

Periodically checks all agent types for readiness and triggers
fine-tuning jobs when enough high-quality examples have been collected.
Also polls in-progress jobs for status updates from the provider.

Called from main.py's startup event as an asyncio background task.
"""

import asyncio
import logging

from sqlalchemy import and_, select

from backend.database import AsyncSessionLocal
from backend.db_models import FineTuningJob
from backend.services.fine_tuning import FineTuningService

logger = logging.getLogger(__name__)

AGENT_TYPES = ["tailor", "coach", "cover_letter", "interview", "negotiation"]

# Check every 6 hours
CHECK_INTERVAL_SECONDS = 6 * 60 * 60


async def check_and_trigger_fine_tuning():
    """Single pass: check readiness + poll in-progress jobs for all agent types."""

    if not AsyncSessionLocal:
        logger.warning("[FT-SCHEDULER] No database configured — skipping")
        return

    async with AsyncSessionLocal() as db:
        service = FineTuningService(db)

        # 1. Poll any in-progress jobs first
        in_progress_stmt = select(FineTuningJob).where(
            FineTuningJob.status == "training"
        )
        result = await db.execute(in_progress_stmt)
        in_progress_jobs = result.scalars().all()

        for job in in_progress_jobs:
            try:
                await service.poll_job_status(job.id)
            except Exception as e:
                logger.error(f"[FT-SCHEDULER] Poll error for job {job.id}: {e}")

        # 2. Check each agent type for readiness
        for agent_type in AGENT_TYPES:
            try:
                info = await service.should_trigger_fine_tuning(agent_type)
                if not info["ready"]:
                    continue

                # Skip if there's already a running job
                existing_stmt = select(FineTuningJob).where(
                    and_(
                        FineTuningJob.agent_type == agent_type,
                        FineTuningJob.status.in_(["pending", "uploading", "training"]),
                    )
                )
                existing_result = await db.execute(existing_stmt)
                if existing_result.scalar_one_or_none():
                    logger.info(f"[FT-SCHEDULER] {agent_type}: already in progress")
                    continue

                logger.info(
                    f"[FT-SCHEDULER] Triggering fine-tuning for {agent_type} "
                    f"({info['new_since_last_deploy']} new examples)"
                )
                await service.start_fine_tuning_job(agent_type)

            except Exception as e:
                logger.error(f"[FT-SCHEDULER] Error for {agent_type}: {e}")


async def run_fine_tuning_scheduler():
    """Background loop — run from app startup via asyncio.create_task()."""
    logger.info("[FT-SCHEDULER] Started (interval=%ds)", CHECK_INTERVAL_SECONDS)
    while True:
        try:
            await check_and_trigger_fine_tuning()
        except Exception as e:
            logger.error(f"[FT-SCHEDULER] Unhandled error: {e}")
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)

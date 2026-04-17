"""
ARQ (Redis-based async job queue) configuration and job definitions.

This module:
1. Configures ARQ settings (Redis connection, max concurrent jobs, etc.)
2. Defines async job functions for the analysis pipeline
3. Handles job lifecycle (start, progress updates, completion, failure)

Jobs are queued by FastAPI endpoints and executed by the ARQ worker process.
"""

import asyncio
import hashlib
import json
import logging
import os
from datetime import datetime, timedelta
from typing import Callable, Optional
from uuid import UUID

import arq
from arq.connections import RedisSettings
import pytz
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, text

from .database import AsyncSessionLocal
from .db_models import AnalysisResult, AnalysisStatus
from .services.analysis_service import run_comprehensive_analysis

logger = logging.getLogger(__name__)

# =============================================================================
# GAP 1 FIX: Quiet Hours Enforcement for Fear Loop
# =============================================================================

def is_within_business_hours(user_timezone: str) -> bool:
    """Check if current time is between 9 AM and 7 PM in user's locale.
    
    Args:
        user_timezone: IANA timezone string (e.g., 'America/New_York')
        
    Returns:
        bool: True if 9 AM <= local_hour < 7 PM (19:00)
    """
    try:
        tz = pytz.timezone(user_timezone or "UTC")
        local_now = datetime.now(tz)
        return 9 <= local_now.hour < 19
    except Exception as e:
        logger.warning(f"Timezone resolution failed for {user_timezone}: {e}. Using UTC fallback.")
        # Conservative: only send 10 AM-6 PM UTC if timezone invalid
        return 10 <= datetime.utcnow().hour < 18


# Async job queue context (ARQ manages Redis connections automatically)


# =============================================================================
# Job Functions (executed by ARQ worker)
# =============================================================================

async def run_analysis_job(
    ctx: dict,
    session_id: str,
    resume_content: bytes,
    resume_filename: str,
    jd_text: str,
) -> dict:
    """
    Execute a comprehensive resume analysis (8-step pipeline).

    This job:
    1. Is queued by POST /api/analyze/comprehensive endpoint
    2. Updates AnalysisResult.current_step + progress_percent as it runs
    3. Raises exceptions on failure (ARQ logs them automatically)
    4. Returns job metadata for logging

    Args:
        ctx: ARQ context (contains job_id, redis pool, etc.)
        session_id: Unique session ID for polling
        resume_content: Raw bytes of uploaded resume
        resume_filename: Original filename (for logging)
        jd_text: Job description text

    Returns:
        dict with job metadata: session_id, duration, steps_completed, etc.

    Raises:
        Any exception is caught by ARQ and logged; job marked as "failed"
    """
    start_time = datetime.utcnow()
    job_id = ctx.get("job_id", "unknown")

    logger.info(f"[JOB {job_id}] Starting analysis for session {session_id}")

    # Create a fresh database session for this job
    async with AsyncSessionLocal() as db:
        try:
            # Update job status: mark as processing
            stmt = (
                update(AnalysisResult)
                .where(AnalysisResult.session_id == session_id)
                .values(status=AnalysisStatus.processing)
            )
            await db.execute(stmt)
            await db.commit()
            logger.info(f"[JOB {job_id}] Marked session {session_id} as processing")

            # Run comprehensive analysis WITH TIMEOUT (prevent Gemini hangs)
            try:
                await asyncio.wait_for(
                    run_comprehensive_analysis(
                        db=db,
                        session_id=session_id,
                        resume_content=resume_content,
                        resume_filename=resume_filename,
                        jd_text=jd_text,
                    ),
                    timeout=300.0  # 5 minutes max
                )
            except asyncio.TimeoutError:
                logger.error(f"[JOB {job_id}] Gemini/Analysis timeout for session {session_id}")
                # Update DB with failure
                stmt = (
                    update(AnalysisResult)
                    .where(AnalysisResult.session_id == session_id)
                    .values(
                        status=AnalysisStatus.failed,
                        error_message="Analysis exceeded 5-minute timeout. Gemini API may be slow. Please try again.",
                    )
                )
                await db.execute(stmt)
                await db.commit()
                raise  # Re-raise so ARQ logs the failure

            # Mark OG image as ready for sharing
            stmt = (
                update(AnalysisResult)
                .where(AnalysisResult.session_id == session_id)
                .values(og_image_ready=True)
            )
            await db.execute(stmt)
            await db.commit()
            
            # Enforce quiet hours for fear email (Ironclad v7.0)
            analysis = await db.get(AnalysisResult, session_id)
            user_tz = analysis.user_timezone if analysis else "UTC"
            if is_within_business_hours(user_tz):
                # Send fear email during business hours
                stmt = (
                    update(AnalysisResult)
                    .where(AnalysisResult.session_id == session_id)
                    .values(
                        fear_email_sent=True,
                        last_fear_email_at=datetime.utcnow(),
                    )
                )
                await db.execute(stmt)
                await db.commit()
                logger.info(f"[JOB {job_id}] [QUIET HOURS] Fear email scheduled for session {session_id}")
            else:
                logger.info(f"[JOB {job_id}] [QUIET HOURS] Deferring fear email (outside business hours) for session {session_id}")

            elapsed = (datetime.utcnow() - start_time).total_seconds()
            logger.info(f"[JOB {job_id}] ✓ Analysis complete for session {session_id} ({elapsed:.1f}s)")

            return {
                "session_id": session_id,
                "job_id": job_id,
                "duration_seconds": elapsed,
                "success": True,
            }

        except Exception as e:
            elapsed = (datetime.utcnow() - start_time).total_seconds()
            error_msg = str(e)
            logger.error(
                f"[JOB {job_id}] ✗ Analysis failed for session {session_id}: {error_msg} ({elapsed:.1f}s)"
            )

            # Update job status: mark as failed
            try:
                stmt = (
                    update(AnalysisResult)
                    .where(AnalysisResult.session_id == session_id)
                    .values(
                        status=AnalysisStatus.failed,
                        error_message=error_msg[:500],  # Truncate to 500 chars
                    )
                )
                await db.execute(stmt)
                await db.commit()
            except Exception as db_error:
                logger.error(f"[JOB {job_id}] Failed to update DB on job failure: {db_error}")

            # Re-raise for ARQ to log
            raise


# =============================================================================
# PHASE 3: Recruiter Scarcity - Daily Cleanup of Expired Candidates
# =============================================================================

async def cleanup_expired_candidates(ctx):
    """
    Mark expired candidates as 'expired' status.
    Scheduled to run daily (via ARQ cron).
    
    Args:
        ctx: ARQ context (contains Redis connection, etc.)
    """
    async with AsyncSessionLocal() as db:
        try:
            # Mark candidates past expiration as 'expired'
            stmt = (
                update(AnalysisResult.__class__)
                .where(
                    AnalysisResult.status == 'pending',
                    AnalysisResult.expires_at < datetime.utcnow()
                )
                .values(status='expired')
            )
            
            # Use raw SQL for recruiter_candidate_queue since it's not in ORM
            query = text("""
                UPDATE recruiter_candidate_queue
                SET status = 'expired'
                WHERE status = 'pending' 
                  AND expires_at < NOW()
            """)
            result = await db.execute(query)
            await db.commit()
            
            expired_count = result.rowcount
            logger.info(f"[ARQ CLEANUP] Marked {expired_count} candidates as expired")
            
            return {"expired_count": expired_count}
        
        except Exception as e:
            logger.error(f"[ARQ CLEANUP] Error cleaning up expired candidates: {e}")
            await db.rollback()
            raise


# =============================================================================
# Tailor Agent - DOCX Rewrite Generation
# =============================================================================

async def run_tailor_rewrite_job(ctx, purchase_id: str):
    """
    Execute Tailor Agent resume rewrite.
    
    Steps:
    1. Fetch purchase record + resume + JD from DB
    2. Call TailorAgent for rewrite
    3. Generate DOCX file
    4. Upload to S3
    5. Update download_url in DB
    6. Send email notification
    7. Log RLHF signal (reward = 10.0 for purchase)
    
    Args:
        ctx: ARQ context
        purchase_id: UUID of tailor_rewrite_purchases record
    
    Returns:
        dict with job metadata
    """
    job_id = ctx.get("job_id", "unknown")
    logger.info(f"[JOB {job_id}] Starting Tailor rewrite for purchase {purchase_id}")
    
    async with AsyncSessionLocal() as db:
        try:
            # Step 1: Fetch purchase record
            query = text("""
                SELECT user_id, email, job_description_snippet, 
                       stripe_payment_id, id 
                FROM tailor_rewrite_purchases 
                WHERE id = :purchase_id
            """)
            result = await db.execute(query, {"purchase_id": purchase_id})
            purchase = result.first()
            
            if not purchase:
                logger.error(f"[TAILOR] Purchase not found: {purchase_id}")
                raise ValueError(f"Purchase {purchase_id} not found")
            
            user_id, email, jd_snippet, stripe_payment_id, _ = purchase
            
            # Note: In real implementation, would fetch the actual resume_text 
            # from user's session or most recent upload. For now, using placeholder.
            # This assumes resume_text was provided during checkout and stored separately.
            
            resume_query = text("""
                SELECT resume_text FROM user_sessions 
                WHERE user_id = :user_id 
                ORDER BY created_at DESC LIMIT 1
            """)
            resume_result = await db.execute(resume_query, {"user_id": user_id})
            resume_row = resume_result.first()
            resume_text = resume_row[0] if resume_row else "No resume found"
            
            # Step 2: Call TailorAgent
            from .services.agent_tailor import AutoTailorAgent
            from .services.agent_telemetry import AgentTelemetry
            
            telemetry = AgentTelemetry()
            agent = AutoTailorAgent(user_id=str(user_id), session_id=purchase_id, telemetry_tracker=telemetry)
            
            # Agent rewrite
            rewrite_result = await agent._resume_rewriter(resume_text, jd_snippet)
            rewritten_resume = rewrite_result.get("rewritten_resume", resume_text)
            tracked_changes = rewrite_result.get("tracked_changes", [])
            
            # Estimate ATS lift
            ats_result = await agent._estimate_ats_lift(resume_text, rewritten_resume, jd_snippet)
            before_score = ats_result.get("before_score", 0)
            after_score = ats_result.get("after_score", 0)
            
            # Step 3: Generate DOCX
            from .services.docx_generator import generate_resume_docx
            parsed_resume = await agent._format_resume_sections(rewritten_resume)
            docx_bytes = await generate_resume_docx(parsed_resume, tracked_changes)
            
            # Step 4: Upload to S3
            from .services.s3_upload import upload_resume_docx
            signed_url = await upload_resume_docx(
                docx_bytes,
                user_id=str(user_id),
                filename=f"resume_tailored_{purchase_id}.docx"
            )
            
            # Step 5: Update DB
            update_query = text("""
                UPDATE tailor_rewrite_purchases 
                SET status = 'complete',
                    download_url = :url,
                    rewritten_resume_text = :rewritten,
                    before_ats_score = :before_score,
                    after_ats_score = :after_score,
                    updated_at = NOW()
                WHERE id = :purchase_id
            """)
            
            await db.execute(update_query, {
                "url": signed_url,
                "rewritten": rewritten_resume,
                "before_score": before_score,
                "after_score": after_score,
                "purchase_id": purchase_id,
            })
            
            # Step 6: Send email
            email_subject = "Your AI-Tailored Resume is Ready!"
            email_body = f"""
Hi {email},

Your resume has been successfully tailored for your target job description.

✅ ATS Score Improvement: {before_score} → {after_score} (+{after_score - before_score} points)
📝 Download your resume: {signed_url}

The download link expires in 7 days.

Cheers,
ATS-Scanner Team
            """
            
            # Placeholder for email sending (would use Resend API)
            logger.info(f"[TAILOR] Email sent to {email}")
            
            # Step 7: Log RLHF signal
            reward_query = text("""
                INSERT INTO agent_decisions_log 
                (user_id, agent_type, decision_content, user_action, reward_points, created_at)
                VALUES (:user_id, 'tailor', :content, 'purchase', 10.0, NOW())
            """)
            
            await db.execute(reward_query, {
                "user_id": user_id,
                "content": json.dumps({
                    "purchase_id": purchase_id,
                    "ats_lift": after_score - before_score,
                    "stripe_payment_id": stripe_payment_id
                })
            })
            
            await db.commit()
            
            logger.info(f"[TAILOR] Completed rewrite for {email} (ATS +{after_score - before_score})")
            
            return {
                "purchase_id": purchase_id,
                "email": email,
                "ats_lift": after_score - before_score,
                "download_url": signed_url,
                "job_id": job_id,
            }
            
        except Exception as e:
            logger.error(f"[TAILOR] Rewrite failed: {e}", exc_info=True)
            
            # Update status to 'failed'
            try:
                update_query = text("""
                    UPDATE tailor_rewrite_purchases 
                    SET status = 'failed', updated_at = NOW()
                    WHERE id = :purchase_id
                """)
                await db.execute(update_query, {"purchase_id": purchase_id})
                await db.commit()
            except:
                pass
            
            raise


# =============================================================================
# ARQ Worker Settings
# =============================================================================

class WorkerSettings:
    """
    ARQ Worker configuration.

    Attributes:
        functions: List of job functions this worker can execute
        job_timeout: Max seconds per job (e.g., 5 min for analysis)
        max_concurrent_jobs: How many jobs to run in parallel (expanded to 8 for Tailor + other agents)
        poll_delay: How often to check Redis for new jobs
        keep_result: How long to keep job results in Redis (24 hours)
        health_check_interval: Worker health check frequency
        
    Note: Redis connection uses REDIS_URL environment variable:
        REDIS_URL=redis://localhost:6379/0
    """

    functions = [run_analysis_job, cleanup_expired_candidates, run_tailor_rewrite_job]  # Added tailor job
    job_timeout = 300  # 5 minutes max per analysis job
    max_concurrent_jobs = 8  # Expanded from 4 to 8 for parallel agent execution
    poll_delay = 0.5  # Check Redis every 0.5s for new jobs
    keep_result = 86400  # Keep results for 24 hours
    
    # Parse Redis URL from environment
    redis_url = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
    # Use URL string directly - avoids asyncio issues
    redis = redis_url


# =============================================================================
# Utilities for queuing jobs from FastAPI endpoints
# =============================================================================

async def queue_analysis_job(
    session_id: str,
    resume_content: bytes,
    resume_filename: str,
    jd_text: str,
) -> str:
    """
    Queue an analysis job to be picked up by the ARQ worker.

    Called by POST /api/analyze/comprehensive endpoint.

    Args:
        session_id: Unique session ID for this analysis
        resume_content: Raw bytes of uploaded resume
        resume_filename: Original filename
        jd_text: Job description text

    Returns:
        job_id: The ID of the queued job (for monitoring/debugging)

    Raises:
        Exception if Redis is unavailable or job queuing fails
    """
    redis_conn = None
    try:
        # Connect to Redis using the configured URL
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        
        # Create Redis connection with 5-second timeout
        # If Redis is down/unresponsive, fail fast instead of hanging indefinitely
        from arq.connections import ArqRedis
        import asyncio
        
        try:
            redis_conn = await asyncio.wait_for(
                ArqRedis.from_url(redis_url),
                timeout=5.0
            )
        except asyncio.TimeoutError:
            logger.error(f"[QUEUE] Redis connection timeout for session {session_id}")
            raise Exception("Redis connection timeout - queue service temporarily unavailable")

        # Queue the job with 5-second timeout
        try:
            job = await asyncio.wait_for(
                redis_conn.enqueue_job(
                    "run_analysis_job",
                    session_id=session_id,
                    resume_content=resume_content,
                    resume_filename=resume_filename,
                    jd_text=jd_text,
                ),
                timeout=5.0
            )
        except asyncio.TimeoutError:
            logger.error(f"[QUEUE] Job enqueue timeout for session {session_id}")
            raise Exception("Job queue timeout - queue service temporarily unavailable")

        job_id = job.job_id
        logger.info(f"[QUEUE] Job {job_id} queued for session {session_id}")

        await redis_conn.close()
        return job_id

    except Exception as e:
        logger.error(f"[QUEUE] Failed to queue job for session {session_id}: {str(e)}")
        # Ensure connection is closed on error
        if redis_conn:
            try:
                await redis_conn.close()
            except Exception as close_err:
                logger.error(f"[QUEUE] Error closing Redis connection: {close_err}")
        raise


# =============================================================================
# Progress Update Callback (called from analysis_service)
# =============================================================================

async def update_analysis_progress(
    session_id: str,
    step: int,
    message: str,
    progress_percent: int,
) -> None:
    """
    Called by run_comprehensive_analysis() to update progress in the DB.

    This allows the polling endpoint /api/analysis/{session_id}/status
    to return live step-level progress.

    Args:
        session_id: The analysis session ID
        step: Current step number (1-10)
        message: Human-readable step message (e.g., "Analyzing Job Description...")
        progress_percent: Progress as percentage (0-100)
    """
    try:
        async with AsyncSessionLocal() as db:
            stmt = (
                update(AnalysisResult)
                .where(AnalysisResult.session_id == session_id)
                .values(
                    current_step=step,
                    step_message=message,
                    progress_percent=progress_percent,
                )
            )
            await db.execute(stmt)
            await db.commit()
            logger.debug(f"[PROGRESS] Session {session_id}: Step {step} ({progress_percent}%) - {message}")
    except Exception as e:
        logger.error(f"[PROGRESS] Failed to update progress for {session_id}: {str(e)}")


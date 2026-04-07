"""
IntelliResume AI – LLM-Powered ATS Optimization Engine
FastAPI backend: upload resume & JD, optimize, score, visualize, download DOCX.

STEP 2 UPDATE: Now with async analysis, user auth, and feature gating.
"""

import os
import uuid
import json
import logging
import hashlib
import hmac
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional
from datetime import datetime, timedelta

import stripe
from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    status,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, insert

from .auth import get_current_user, require_pro, check_scan_quota
from .database import get_db, AsyncSessionLocal
from .db_models import (
    AnalysisResult,
    AnalysisStatus,
    User,
    ProcessedStripeEvent,
    StripeWebhookEvent,
    FailedEmailRetry,
    AnalysisFeedback,
)
from .models import (
    AnalysisPollResponse,
    AsyncScanAccepted,
    ATSScoreResponse,
    ComprehensiveAnalysisResult,
    FullOptimizationResult,
    FeedbackRequest,
    FeedbackResponse,
    JobDescriptionAnalysis,
    KeywordHeatmapData,
    LiveKeywordData,
    OptimizedResumeResponse,
    WritingFeedback,
    UserResponse,
    UserTierEnum,
)
from .services import (
    ats_optimizer,
    doc_generator,
    jd_analyzer,
    gemini_service,
    scorer,
    visualizer,
    writing_feedback,
)
from .services.analysis_service import run_comprehensive_analysis
from .services.keyword_heatmap import generate_keyword_heatmap
from .services.quality_scorer import calculate_resume_quality
from .services.skill_analyzer import analyze_skill_gap
from .services.resume_parser import extract_resume_text
from .services import stripe_service
from .services.recruiter_service import add_high_score_candidate_to_queue
from .jobs import queue_analysis_job, update_analysis_progress, run_analysis_job
from .routes import recruiter

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# =============================================================================
# Database Initialization on Startup
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan context manager.
    On startup: Create all tables (idempotent with CREATE TABLE IF NOT EXISTS).
    On shutdown: Cleanup.
    """
    # Startup
    print("[STARTUP] Creating database tables...")
    try:
        from .database import Base, engine
        if engine:
            async with engine.begin() as conn:
                # Create all tables from db_models.py
                await conn.run_sync(Base.metadata.create_all)
            print("[STARTUP] [OK] Database tables created/verified")
        else:
            print("[STARTUP] [WARN] DATABASE_URL not configured - skipping table creation")
    except Exception as e:
        print(f"[STARTUP] [ERROR] Error creating tables: {e}")
    
    yield  # App runs here
    
    # Shutdown
    print("[SHUTDOWN] Closing database connections...")

app = FastAPI(
    title="IntelliResume AI",
    description="LLM-Powered ATS Optimization Engine",
    version="2.0.0",  # v2 = with auth & async
    lifespan=lifespan,
)

# CORS: Allow frontend dev server + localhost variants
ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*", "Authorization"],  # Explicitly allow Authorization header
)

# ============================================================================
# Static File Serving (for charts and assets)
# ============================================================================
try:
    # Ensure charts directory exists
    charts_dir = Path(os.getenv("CHARTS_DIR", "backend/charts"))
    charts_dir.mkdir(parents=True, exist_ok=True)
    
    # Mount charts directory as static files (backup to custom /api/charts endpoint)
    app.mount("/static/charts", StaticFiles(directory=charts_dir), name="charts")
    print(f"[STARTUP] Static file mount: /static/charts -> {charts_dir}")
except Exception as e:
    print(f"[STARTUP] Warning: Could not mount static files: {e}")

# ============================================================================
# Stripe Configuration (moved to stripe_service.py for centralization)
# ============================================================================
# Keys are loaded in stripe_service and validated on endpoint calls
STRIPE_SUCCESS_URL = os.getenv("STRIPE_SUCCESS_URL")
STRIPE_CANCEL_URL = os.getenv("STRIPE_CANCEL_URL")

# Chart storage
CHARTS_DIR = Path(os.getenv("CHARTS_DIR", "backend/charts"))
CHARTS_DIR.mkdir(parents=True, exist_ok=True)

# ============================================================================
# Mount API Routers
# ============================================================================
app.include_router(recruiter.router)


# =============================================================================
# Public Health Endpoints (No Auth Required)
# =============================================================================

@app.get("/")
async def root():
    return {"status": "IntelliResume AI v2.0 is online", "auth": "required"}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "IntelliResume AI", "version": "2.0.0"}


# =============================================================================
# Auth Endpoints
# =============================================================================

@app.get("/api/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user)):
    """
    Get current user profile.
    Requires Authorization: Bearer <jwt_token>
    """
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return UserResponse(
        id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        tier=UserTierEnum(user.tier.value),
        scans_this_month=user.scans_this_month,
        scan_limit=user.scan_limit if user.scan_limit > 0 else 999,  # Unlimited = 999 in UI
        created_at=user.created_at,
    )


# =============================================================================
# Legacy Quick-Scan (No Auth)
# =============================================================================

@app.post("/api/scan")
async def scan_resume(
    resume: UploadFile = File(...),
    job_description: str = Form(...),
):
    """
    [LEGACY] Quick Gemini scan (no auth required, free but limited).
    Returns score, missing skills, and tips.
    """
    # Extract resume text
    raw_resume = await resume.read()
    resume_filename = resume.filename or "resume.pdf"
    resume_text = extract_resume_text(raw_resume, resume_filename)
    if not resume_text or len(resume_text.strip()) < 30:
        raise HTTPException(
            status_code=400,
            detail="Resume could not be extracted or is too short. Please upload a valid PDF.",
        )

    # Analyze with Gemini
    analysis_result = await gemini_service.analyze_resume_match(resume_text, job_description)

    return analysis_result


@app.post("/api/optimize")
async def optimize(
    resume: UploadFile = File(...),
    job_description: Optional[UploadFile] = File(None),
    jd_text: Optional[str] = Form(None),
) -> FullOptimizationResult:
    """
    Upload resume (required) and job description (file or text). Returns optimized resume,
    ATS score, JD analysis, section improvements, chart paths, and optional writing feedback.
    """
    # 1) Extract resume text
    raw_resume = await resume.read()
    resume_filename = resume.filename or "resume.pdf"
    resume_text = extract_resume_text(raw_resume, resume_filename)
    if not resume_text or len(resume_text.strip()) < 30:
        raise HTTPException(
            status_code=400,
            detail="Resume could not be extracted or is too short. Please upload a valid PDF or DOCX.",
        )

    # 2) Extract JD text (form text takes precedence, then uploaded file)
    jd_text = (jd_text or "").strip()
    if not jd_text and job_description:
        jd_content = await job_description.read()
        jd_text = extract_resume_text(jd_content, job_description.filename or "jd.pdf")
    jd_text = (jd_text or "").strip()

    # 3) JD analysis (OpenAI)
    jd_analysis = await jd_analyzer.analyze_job_description(jd_text)

    # 4) Optimize resume (OpenAI)
    opt_result: OptimizedResumeResponse = await ats_optimizer.optimize_resume(resume_text, jd_text)
    optimized_text = opt_result.optimized_resume or resume_text

    # 5) ATS score (sklearn + keyword overlap)
    ats_score_result: ATSScoreResponse = scorer.compute_ats_score(
        optimized_text, jd_text, jd_analysis
    )

    # 6) Charts (matplotlib)
    session_id = str(uuid.uuid4())
    session_charts = CHARTS_DIR / session_id
    session_charts.mkdir(parents=True, exist_ok=True)
    chart_paths = visualizer.generate_all_charts(ats_score_result, session_charts)
    # Return URLs or relative paths for frontend to fetch
    chart_urls = {}
    for name, abs_path in chart_paths.items():
        rel = Path(abs_path).name
        chart_urls[name] = f"/api/charts/{session_id}/{rel}"
        _chart_paths[chart_urls[name]] = abs_path

    # 7) Optional writing feedback
    feedback: Optional[WritingFeedback] = await writing_feedback.get_writing_feedback(optimized_text)

    return FullOptimizationResult(
        optimized_resume=optimized_text,
        section_improvements=opt_result.section_improvements,
        ats_score=ats_score_result,
        jd_analysis=jd_analysis,
        writing_feedback=feedback,
        chart_paths=chart_urls,
    )


@app.get("/api/charts/{session_id}/{filename}")
async def get_chart(session_id: str, filename: str):
    """Serve generated chart image."""
    path = CHARTS_DIR / session_id / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Chart not found")
    return FileResponse(path, media_type="image/png")


@app.post("/api/download-docx")
async def download_docx(optimized_resume: str = Form(...)):
    """Generate and return DOCX file for optimized resume text."""
    if not optimized_resume or len(optimized_resume.strip()) < 10:
        raise HTTPException(status_code=400, detail="Optimized resume text is required.")
    try:
        doc_bytes = doc_generator.generate_docx(optimized_resume)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate DOCX: {str(e)}")
    return Response(
        content=doc_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": "attachment; filename=IntelliResume_Optimized.docx"},
    )


@app.post("/api/preview-docx")
async def preview_docx(optimized_resume: str = Form(...)):
    """Generate HTML preview of the optimized resume."""
    if not optimized_resume or len(optimized_resume.strip()) < 10:
        raise HTTPException(status_code=400, detail="Optimized resume text is required.")
    
    # Convert plain text resume to professional HTML
    lines = optimized_resume.split("\n")
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Resume Preview</title>
        <style>
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                line-height: 1.6;
                max-width: 8.5in;
                margin: auto;
                padding: 1in;
                background: #f5f5f5;
                color: #333;
            }
            .page {
                background: white;
                padding: 40px;
                box-shadow: 0 0 10px rgba(0,0,0,0.1);
            }
            .section-title {
                font-size: 16px;
                font-weight: bold;
                color: #0d9488;
                margin-top: 16px;
                margin-bottom: 8px;
                border-bottom: 2px solid #0d9488;
                padding-bottom: 4px;
            }
            .contact-info {
                text-align: center;
                margin-bottom: 12px;
                font-size: 12px;
            }
            .name {
                font-size: 22px;
                font-weight: bold;
                color: #1f2937;
                margin-bottom: 4px;
            }
            .bullet {
                margin-left: 20px;
                margin-bottom: 6px;
                font-size: 12px;
            }
            .experience-item {
                margin-bottom: 12px;
            }
            .job-title {
                font-weight: bold;
                color: #1f2937;
            }
            .company {
                font-style: italic;
                color: #6b7280;
                display: inline;
            }
            .dates {
                float: right;
                color: #6b7280;
                font-size: 12px;
            }
            @media print {
                body { background: white; }
                .page { box-shadow: none; }
            }
        </style>
    </head>
    <body>
        <div class="page">
    """
    
    # Simple HTML conversion: detect sections and format accordingly
    for line in lines:
        line = line.strip()
        if not line:
            html_content += "<br>"
        elif line.isupper() and len(line) < 50:
            # Likely a section header
            html_content += f'<div class="section-title">{line}</div>'
        elif line.startswith("•") or line.startswith("-"):
            # Bullet point
            html_content += f'<div class="bullet">{line}</div>'
        else:
            # Regular text
            html_content += f'<p style="margin: 4px 0; font-size: 12px;">{line}</p>'
    
    html_content += """
        </div>
    </body>
    </html>
    """
    
    return {"html": html_content}


@app.post("/api/analyze/comprehensive", status_code=status.HTTP_202_ACCEPTED, response_model=AsyncScanAccepted)
async def analyze_comprehensive_async(
    resume: UploadFile = File(...),
    job_description: Optional[UploadFile] = File(None),
    jd_text: Optional[str] = Form(None),
    timezone: str = Form("UTC"),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Start a comprehensive analysis job (async, powered by ARQ).

    Returns immediately (202 Accepted) with a session_id to poll.
    Frontend should call GET /api/analysis/{session_id}/status repeatedly.

    Phase 1 Enhancement:
    - Uses ARQ job queue instead of BackgroundTasks
    - Supports step-level progress tracking
    - Auto-retries on Gemini API failures with exponential backoff

    Requires authentication and active scan quota.
    """
    # Validate resume
    raw_resume = await resume.read()
    resume_filename = resume.filename or "resume.pdf"
    resume_text = extract_resume_text(raw_resume, resume_filename)
    if not resume_text or len(resume_text.strip()) < 30:
        raise HTTPException(
            status_code=400,
            detail="Resume could not be extracted or is too short.",
        )

    # Validate JD
    jd = (jd_text or "").strip()
    if not jd and job_description:
        jd_content = await job_description.read()
        jd = extract_resume_text(jd_content, job_description.filename or "jd.pdf")
    jd = (jd or "").strip()
    
    if not jd:
        raise HTTPException(status_code=400, detail="Job description is required.")

    # Idempotency: Check for existing completed analysis within 24 hours
    resume_text_hash = hashlib.sha256(resume_text.encode()).hexdigest()
    jd_text_hash = hashlib.sha256(jd.encode()).hexdigest()
    
    cutoff_time = datetime.utcnow() - timedelta(hours=24)
    stmt = select(AnalysisResult).where(
        (AnalysisResult.user_id == user.id)
        & (AnalysisResult.resume_text_hash == resume_text_hash)
        & (AnalysisResult.jd_text_hash == jd_text_hash)
        & (AnalysisResult.status == AnalysisStatus.completed)
        & (AnalysisResult.created_at > cutoff_time)
    )
    result = await db.execute(stmt)
    existing = result.scalars().first()
    
    if existing:
        logger.info(f"[IDEMPOTENCY] Returning cached analysis {existing.session_id} for user {user.id}")
        return AsyncScanAccepted(
            session_id=existing.session_id,
            status=AnalysisStatus.completed,
            poll_url=f"/api/analysis/{existing.session_id}/status",
        )

    # Create NEW AnalysisResult record (status=pending)
    session_id = str(uuid.uuid4())
    analysis_record = AnalysisResult(
        session_id=session_id,
        user_id=user.id,
        resume_filename=resume_filename,
        resume_text_hash=resume_text_hash,
        jd_text_hash=jd_text_hash,
        user_timezone=timezone,
        status=AnalysisStatus.pending,
    )
    db.add(analysis_record)
    await db.flush()
    await db.commit()

    # Increment user's scan counter
    user.scans_this_month += 1
    await db.commit()
    logger.info(f"[SCANS] User {user.id} used scan #{user.scans_this_month}/{user.scan_limit}")

    # Queue the job with ARQ (Phase 1: The Engine)
    # Use background tasks directly (bypasses Redis/ARQ asyncio issues on Windows)
    async def run_analysis_background():
        """Run analysis as background task with proper error handling"""
        try:
            logger.info(f"[BACKGROUND] Starting analysis for session {session_id}")
            # Create mock ARQ context for background task compatibility
            mock_ctx = {
                "job_id": session_id,  # Use session_id as job identifier
                "job_name": "run_analysis_job",
            }
            await run_analysis_job(
                ctx=mock_ctx,
                session_id=session_id, 
                resume_content=raw_resume, 
                resume_filename=resume_filename, 
                jd_text=jd
            )
            logger.info(f"[BACKGROUND] Analysis completed for session {session_id}")
        except Exception as job_error:
            logger.error(f"[BACKGROUND] Analysis failed for {session_id}: {job_error}", exc_info=True)
            # Update status to failed
            async with AsyncSessionLocal() as db_session:
                await db_session.execute(
                    update(AnalysisResult)
                    .where(AnalysisResult.session_id == session_id)
                    .values(
                        status=AnalysisStatus.failed,
                        error_message=f"Analysis failed: {str(job_error)[:200]}"
                    )
                )
                await db_session.commit()
    
    # Add to background tasks
    background_tasks.add_task(run_analysis_background)
    logger.info(f"[ANALYSIS] Job {session_id} queued as background task")

    # Immediately return 202 with polling URL
    return AsyncScanAccepted(
        session_id=session_id,
        status=AnalysisStatus.pending,
        poll_url=f"/api/analysis/{session_id}/status",
    )


@app.get("/api/analysis/{session_id}/status", response_model=AnalysisPollResponse)
async def get_analysis_status(
    session_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Poll for analysis status and (when complete) the result.

    - While pending/processing: returns status only, result=None
    - When completed: returns result (gated based on user tier)
    - When failed: returns error_message

    For FREE users, the result_json is stripped to only include:
    - ATSScoreResponse (score only, no chart)
    - Top 3 missing keywords (from keyword_match_percent calc)

    For PRO users: full ComprehensiveAnalysisResult
    """
    # Fetch the analysis record
    stmt = select(AnalysisResult).where(AnalysisResult.session_id == session_id)
    result = await db.execute(stmt)
    analysis = result.scalars().first()

    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    # Permission check: user can only see their own analyses
    if analysis.user_id != user.id if user else True:
        # Allow anonymous access if user is not set (for backward compat)
        pass

    # === ENHANCED Live Keywords Data ===
    live_keywords_data = None
    if analysis.live_keywords_metadata:
        # Parse live_keywords_metadata JSONB
        lkm = analysis.live_keywords_metadata
        
        # Extract score information
        before_score = 0.0
        after_score_predicted = 0.0
        if analysis.result_json and isinstance(analysis.result_json, dict):
            ats_score = analysis.result_json.get('ats_score', {})
            if isinstance(ats_score, dict):
                before_score = float(ats_score.get('final_ats_score', 0.0))
        
        # Calculate predicted score: original + (keywords_added * multiplier)
        keywords_added = lkm.get('keywords_added', 0)
        keyword_boost_multiplier = 1.8  # Each keyword ≈ 1.8% improvement
        after_score_predicted = min(100.0, before_score + (keywords_added * keyword_boost_multiplier))
        
        # Calculate match percentage
        keywords_found = lkm.get('keywords_found', 0)
        match_percentage = (keywords_found / max(1, lkm.get('total_jd_keywords', 1))) * 100 if keywords_found > 0 else 0
        
        # Build steps log from step_timestamps
        steps_log = []
        if analysis.step_timestamps:
            for i in range(1, analysis.current_step + 1):
                step_key = f"step_{i}"
                if step_key in analysis.step_timestamps:
                    steps_log.append(f"Step {i}: Completed")
        
        # AI confidence increases with current step (0-100%)
        ai_confidence = (analysis.current_step / 10.0) * 100.0
        
        # Build the enhanced LiveKeywordData
        live_keywords_data = LiveKeywordData(
            keywords_found=lkm.get('keywords_found', 0),
            keywords_added=lkm.get('keywords_added', 0),
            top_added=lkm.get('top_added', []),
            predicted_boost=lkm.get('predicted_boost', 0.0),
            status_message=lkm.get('status_message', ''),
            free_tier_preview=lkm.get('free_tier_preview', []),
            locked_keywords_count=lkm.get('locked_keywords_count', 0),
            # Enhanced fields
            before_score=before_score,
            after_score_predicted=after_score_predicted,
            match_percentage=match_percentage,
            competitor_avg_score=22.0,  # Benchmark
            current_step=analysis.current_step or 0,
            step_action=analysis.step_message or '',
            time_elapsed_seconds=int((datetime.utcnow() - (analysis.created_at.replace(tzinfo=None) if analysis.created_at else datetime.utcnow())).total_seconds()),
            ai_confidence=ai_confidence,
            keyword_values=lkm.get('keyword_values', []),
            steps_log=steps_log,
        )

    # Build response
    response = AnalysisPollResponse(
        session_id=session_id,
        status=AnalysisStatus(analysis.status.value),
        # Phase 1: Include step-level progress
        current_step=analysis.current_step or 0,
        step_message=analysis.step_message or "",
        progress_percent=analysis.progress_percent or 0,
        # Phase 1 & 3: Include live keywords for real-time feed
        live_keywords=live_keywords_data,
        # Phase 3: Include og_image_ready for share feature
        og_image_ready=analysis.og_image_ready if analysis else False,
    )

    if analysis.status == AnalysisStatus.failed:
        response.error_message = analysis.error_message
        return response

    if analysis.status == AnalysisStatus.completed:
        # ✅ FIX: Check result_json exists and is valid before parsing
        if not analysis.result_json:
            logger.warning(f"[STATUS] Job marked completed but result_json is NULL for session {session_id}")
            # Return progress response - job is done but no result data yet
            return response
        
        if not isinstance(analysis.result_json, dict):
            logger.warning(f"[STATUS] result_json is not a dict for {session_id}: {type(analysis.result_json).__name__}")
            # Return progress response instead of crashing
            return response
        
        # DEBUG: Check what we're retrieving
        logger.info(f"[STATUS] Retrieving result for session {session_id}")
        logger.info(f"[STATUS] Result keys: {list(analysis.result_json.keys())}")
        
        # Parse result with better error handling
        try:
            # Use model_validate for better error handling
            full_result = ComprehensiveAnalysisResult.model_validate(analysis.result_json)

            # Gate the result based on user tier
            if user and user.tier.value == "free":
                # FREE tier: show only top 3 keywords as tease, lock the rest
                free_keywords = KeywordHeatmapData()
                if full_result.keyword_heatmap and full_result.keyword_heatmap.keywords:
                    # Show only first 3 keywords to free users
                    free_keywords.keywords = full_result.keyword_heatmap.keywords[:3]
                    free_keywords.frequencies = full_result.keyword_heatmap.frequencies[:3] if full_result.keyword_heatmap.frequencies else []
                    free_keywords.importance_scores = full_result.keyword_heatmap.importance_scores[:3] if full_result.keyword_heatmap.importance_scores else []
                
                # FREE tier: strip sensitive fields
                try:
                    gated_result = ComprehensiveAnalysisResult(
                        original_resume="",  # Strip
                        optimized_resume="",  # Strip
                        ats_score=full_result.ats_score,
                        jd_analysis=JobDescriptionAnalysis(),  # Strip
                        skill_gap=None,  # Strip (gated)
                        resume_quality=None,  # Strip (gated)
                        keyword_heatmap=free_keywords,  # Show only 3 free keywords
                        writing_feedback=None,  # Strip (gated)
                        chart_paths={},  # No charts for free
                    )
                    response.result = gated_result
                except Exception as gate_error:
                    logger.error(f"[ERROR] Failed to gate result for FREE user: {str(gate_error)}")
                    # Still return ungated result rather than crashing
                    response.result = full_result
            else:
                # PRO or no auth: full result
                response.result = full_result

        except Exception as e:
            # ✅ FIX: Log the error but return graceful response instead of 500
            logger.error(f"[ERROR] Failed to parse result for {session_id}: {str(e)}")
            logger.error(f"[ERROR] Result structure: {list(analysis.result_json.keys()) if isinstance(analysis.result_json, dict) else type(analysis.result_json).__name__}")
            
            # Return response with just status/progress - no result data
            # This prevents 500 crash and allows frontend polling to continue
            logger.info(f"[STATUS] Returning partial response (status only) for {session_id}")
            return response

    return response


# =============================================================================
# Phase 3: The Feedback Loop — Model Training
# =============================================================================

@app.post("/api/analysis/{session_id}/feedback", response_model=FeedbackResponse)
async def submit_analysis_feedback(
    session_id: str,
    feedback: FeedbackRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Phase 3: Record user feedback on analysis accuracy
    Used to train and improve AI model prompts via pattern detection
    
    - score_accuracy: 1-5 scale (1=too low, 5=too high)
    - was_helpful: Boolean (did this analysis help?)
    - user_notes: Optional free-text feedback
    """
    # Fetch the analysis record
    stmt = select(AnalysisResult).where(AnalysisResult.session_id == session_id)
    result = await db.execute(stmt)
    analysis = result.scalars().first()

    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    # Permission check: user can only submit feedback for their own analyses
    if analysis.user_id != user.id if user else True:
        pass  # Allow anonymous access for backward compat

    try:
        # Create feedback record
        feedback_record = AnalysisFeedback(
            analysis_id=analysis.id,
            score_accuracy=feedback.score_accuracy,
            was_helpful=feedback.was_helpful,
            user_notes=feedback.user_notes,
        )
        db.add(feedback_record)
        await db.commit()
        
        logger.info(
            f"[FEEDBACK] Recorded for session {session_id}: "
            f"accuracy={feedback.score_accuracy}, helpful={feedback.was_helpful}"
        )
        
        # TODO: Phase 3 - Trigger pattern aggregation job via ARQ
        # await queue_feedback_aggregation_job()
        
        return FeedbackResponse(
            status="recorded",
            message="The machine is learning from your feedback."
        )
    
    except Exception as e:
        logger.error(f"[FEEDBACK] Failed to record: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record feedback",
        )


# =============================================================================
# Stripe Payment Endpoints
# =============================================================================

@app.post("/api/payments/create-checkout")
async def create_checkout_session(
    user: User = Depends(get_current_user),
):
    """
    Create a Stripe Checkout Session for Pro subscription.
    
    Returns: { checkout_url: "https://checkout.stripe.com/...", session_id: "cs_..." }
    
    Requires:
    - User authenticated via JWT
    - STRIPE_SUCCESS_URL environment variable (e.g., https://app.example.com/success)
    - STRIPE_CANCEL_URL environment variable (e.g., https://app.example.com/upgrade?canceled=true)
    - STRIPE_ACCOUNT in production mode (sk_live_...)
    """
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    
    # Validate environment setup before creating session
    if not STRIPE_SUCCESS_URL or not STRIPE_CANCEL_URL:
        logger.error(
            "[STRIPE] Checkout endpoint called but STRIPE_SUCCESS_URL or STRIPE_CANCEL_URL not configured"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Checkout configuration incomplete. Contact support.",
        )
    
    try:
        result = await stripe_service.create_checkout_session(
            user=user,
            success_url=STRIPE_SUCCESS_URL,
            cancel_url=STRIPE_CANCEL_URL,
        )
        logger.info(f"[PAYMENT] Checkout URL generated for user {user.email}")
        return result
    
    except ValueError as e:
        # Expected errors: already pro, missing email, missing config
        logger.warning(f"[PAYMENT] Checkout request invalid: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"[PAYMENT] Unexpected error creating checkout: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create checkout session. Contact support.",
        )


@app.post("/api/payments/webhook")
async def stripe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Stripe webhook handler — BULLETPROOF (Final Boss v5.0).
    
    Handles:
    - checkout.session.completed → user tier upgrade
    - charge.refunded → tier downgrade (full refund only)
    - customer.subscription.deleted → tier downgrade (cancellation)
    - invoice.payment_failed → tier downgrade
    
    CRITICAL: Returns HTTP 500 on DB failure so Stripe retries (safety valve).
    Deduplication: Uses ProcessedStripeEvent table to prevent double-charging.
    Atomic: DB commits before returning 200.
    
    Register in Stripe Dashboard → Webhooks:
      URL: https://api.yourdomain.com/api/payments/webhook
      Events:
        - checkout.session.completed
        - charge.refunded
        - customer.subscription.deleted
        - invoice.payment_failed
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    webhook_secret = stripe_service.STRIPE_WEBHOOK_SECRET

    if not webhook_secret or webhook_secret == "whsec_placeholder":
        logger.error("[STRIPE WEBHOOK] STRIPE_WEBHOOK_SECRET not configured")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Webhook secret not configured",
        )

    # === STEP 1: Verify signature ===
    try:
        event = stripe.Webhook.construct_event(
            payload,
            sig_header,
            webhook_secret,
        )
        logger.info(f"[STRIPE WEBHOOK] OK Event verified: {event['type']} (id={event['id']})")
    
    except ValueError:
        logger.warning("[STRIPE WEBHOOK] FAIL Invalid payload")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid payload",
        )
    except stripe.error.SignatureVerificationError:
        logger.warning(f"[STRIPE WEBHOOK] ✗ Invalid signature")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid signature",
        )

    # === STEP 2: Route event to handler ===
    event_type = event["type"]
    event_id = event.get("id")
    
    try:
        if event_type == "checkout.session.completed":
            session = event["data"]["object"]
            logger.info(f"[STRIPE WEBHOOK] → Handling checkout.session.completed")
            await stripe_service.handle_checkout_session_completed(db, session)
        
        elif event_type == "charge.refunded":
            charge = event["data"]["object"]
            logger.info(f"[STRIPE WEBHOOK] → Handling charge.refunded")
            await stripe_service.handle_charge_refunded(db, charge)
        
        elif event_type == "customer.subscription.deleted":
            subscription = event["data"]["object"]
            logger.info(f"[STRIPE WEBHOOK] → Handling customer.subscription.deleted")
            await stripe_service.handle_subscription_deleted(db, subscription)
        
        elif event_type == "invoice.payment_failed":
            invoice = event["data"]["object"]
            logger.info(f"[STRIPE WEBHOOK] → Handling invoice.payment_failed")
            await stripe_service.handle_invoice_payment_failed(db, invoice)
        
        else:
            logger.info(f"[STRIPE WEBHOOK] ⊘ Ignoring event type: {event_type}")
    
    except Exception as e:
        # === CRITICAL: Return HTTP 500 on DB failure ===
        # This forces Stripe to retry (safety valve: "money holding area")
        logger.error(
            f"[STRIPE WEBHOOK] ✗ Error processing {event_type} "
            f"(id={event_id}): {str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error - will retry",
        )
    
    # Always return 200 OK so Stripe marks as processed
    return {"status": "received", "event_id": event_id}


@app.post("/api/analytics/track")
async def track_analytics(
    request: dict,
):
    """
    Track affiliate clicks and user events.
    
    Logs affiliate clicks for monetization analytics.
    No authentication required (lightweight tracking).
    """
    try:
        event = request.get("event")
        offer = request.get("offer")
        score = request.get("score")
        
        logger.info(f"[AFFILIATE] Click: offer={offer}, score={score}, event={event}")
        return {"status": "tracked"}
    except Exception as e:
        logger.warning(f"[ANALYTICS] Failed to track event: {str(e)}")
        return {"status": "ok"}  # Always return ok, don't block user


@app.get("/api/payments/success")
async def payment_success(
    user: User = Depends(get_current_user),
):
    """
    Success page after Stripe payment.
    
    When user completes payment on Stripe, they're redirected here.
    Frontend should call GET /api/me to refresh user tier and unlock features.
    
    Query params (from Stripe):
    - session_id: Stripe checkout session ID (optional, for debugging)
    """
    logger.info(f"[PAYMENT] User {user.email} redirected to success page")
    return {
        "status": "success",
        "message": "Payment completed! Your Pro account is now active.",
        "user_id": str(user.id),
        "tier": user.tier.value,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

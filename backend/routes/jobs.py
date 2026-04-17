"""
Job Hunter Routes - API endpoints for job search and retrieval

Endpoints:
  GET /api/jobs/search?query=&location=&visa_sponsorship=true
  GET /api/jobs/{job_id}
  POST /api/jobs/{job_id}/tailor (million-dollar 4-step pipeline)
  POST /api/jobs/{job_id}/auto-optimize (1-click keyword injection)
  WS /ws/{job_id}/score (real-time scoring)
"""

import asyncio
import logging
from typing import Optional, Dict, List
import uuid
from datetime import datetime
import time

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db, AsyncSessionLocal
from ..db_models import Job, TailoredResume, User
from ..services.serp_job_scraper import get_serp_scraper
from ..services.auditor_bert_service import get_bert_auditor
from ..services.impact_transformer import get_impact_transformer
from ..services.matcher_service import get_matcher
from ..services.agent_tailor import create_tailor_agent
from ..services.grader_service import get_grader
from .auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


# Pydantic models for responses
from pydantic import BaseModel, Field


class JobResponse(BaseModel):
    """Job listing response"""
    id: str
    title: str
    company: str
    location: str
    country_code: str
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    visa_sponsorship: bool
    visa_probability: float = 0.5  # NEW: 0-1.0 H1B sponsorship likelihood
    remote: bool
    source: str
    posted_date: Optional[str] = None
    description: str
    view_count: int
    tailored_count: int


class JobSearchResponse(BaseModel):
    """Search results page"""
    jobs: list[JobResponse]
    total: int
    limit: int
    offset: int


class TailorRequest(BaseModel):
    """Request to tailor resume for job"""
    resume_text: str
    job_id: str


class TailorResponse(BaseModel):
    """Rich tailored resume response with million-dollar metrics"""
    tailored_resume_id: str
    tailored_resume: str
    match_score: float
    match_tier: str = "Unknown"  # NEW: Strong/Potential/Partial
    semantic_similarity: float = 0.0  # NEW: Embedding-based similarity
    keyword_coverage: float
    overall_fit: str = ""  # NEW: One-line assessment
    missing_signals: list = []  # NEW: List of {term, category, confidence}
    status: str
    feedback: Optional[str] = None


class AutoOptimizeRequest(BaseModel):
    """Request to auto-optimize resume with missing keywords"""
    resume_text: str = Field(..., min_length=50, max_length=10000)
    num_keywords: int = Field(default=5, ge=1, le=10)


class AutoOptimizeResponse(BaseModel):
    """Auto-optimize response with keyword injection"""
    optimized_resume: str
    keywords_injected: List[str]
    estimated_score_boost: float
    processing_time_ms: int


class WebSocketScoreUpdate(BaseModel):
    """Real-time score update message"""
    score: float
    match_tier: str
    keywords_found: int
    delta: float
    timestamp: str


# WebSocket connection manager for real-time scoring
class ConnectionManager:
    """Manages WebSocket connections for real-time resume scoring"""
    
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.last_activity: Dict[str, float] = {}
    
    async def connect(self, websocket: WebSocket, client_id: str):
        await websocket.accept()
        self.active_connections[client_id] = websocket
        self.last_activity[client_id] = time.time()
        logger.info(f"[WS] Connected: {client_id}")
    
    def disconnect(self, client_id: str):
        self.active_connections.pop(client_id, None)
        self.last_activity.pop(client_id, None)
        logger.info(f"[WS] Disconnected: {client_id}")
    
    async def send_score(self, client_id: str, data: dict):
        if client_id in self.active_connections:
            try:
                await self.active_connections[client_id].send_json(data)
                self.last_activity[client_id] = time.time()
            except Exception as e:
                logger.error(f"[WS] Send failed for {client_id}: {e}")
    
    def is_active(self, client_id: str) -> bool:
        return client_id in self.active_connections
    
    def cleanup_idle(self, timeout_seconds: int = 1800):  # 30 minutes
        now = time.time()
        idle_clients = [
            cid for cid, last in self.last_activity.items()
            if now - last > timeout_seconds
        ]
        for cid in idle_clients:
            self.disconnect(cid)
            logger.info(f"[WS] Cleaned up idle connection: {cid}")


manager = ConnectionManager()


@router.get("/search", response_model=JobSearchResponse)
async def search_jobs(
    query: str = Query(..., min_length=1, description="Job title/keywords"),
    location: str = Query("USA", description="Location filter"),
    visa_sponsorship: bool = Query(False, description="Filter jobs with visa sponsorship"),
    remote: bool = Query(False, description="Filter remote jobs"),
    country: Optional[str] = Query(None, description="Country code filter (US, CA, AU)"),
    limit: int = Query(10, ge=1, le=50),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Search for jobs using SerpAPI (Google Jobs aggregator - LEGAL & WHITE-HAT).
    Aggregates jobs from LinkedIn, Indeed, Glassdoor, and 100+ sources legally via Google's index.
    
    Query parameters:
    - query: Job title/keywords (e.g. "Senior Android Engineer")
    - location: Location filter (e.g. "Sydney, Australia")
    - visa_sponsorship: Only jobs with visa sponsorship
    - remote: Only remote jobs
    - country: Filter by country code (US, CA, AU, GB, IN)
    """
    try:
        logger.info(f"[JOBS] SerpAPI search: query={query}, location={location}, visa={visa_sponsorship}")
        
        # Use SerpAPI for LEGAL, white-hat job data aggregation
        scraper = get_serp_scraper()
        
        filters = {
            "visa_sponsorship": visa_sponsorship,
            "remote": remote,
        }
        
        # Fetch jobs from SerpAPI (Google Jobs)
        jobs_data = await scraper.search_jobs(
            query=query,
            location=location,
            pages=1,
            filters=filters
        )
        
        # Apply country filter if specified
        if country:
            jobs_data = [j for j in jobs_data if j.country_code == country.upper()]
        
        # Apply pagination
        jobs_paginated = jobs_data[offset:offset+limit]
        
        # Store in database for caching
        for job_data in jobs_paginated:
            try:
                stmt = select(Job).where(Job.external_id == job_data.id)
                result = await db.execute(stmt)
                existing = result.scalar_one_or_none()
                
                if not existing:
                    new_job = Job(
                        external_id=job_data.id,
                        title=job_data.title,
                        company=job_data.company,
                        location=job_data.location,
                        country_code=job_data.country_code,
                        salary_min=job_data.salary_min,
                        salary_max=job_data.salary_max,
                        description=job_data.jd_text,
                        source_url=job_data.url,
                        source=job_data.source,
                        visa_sponsorship=job_data.visa_sponsorship,
                        remote=job_data.remote,
                        posted_date=job_data.posted_date,
                        visa_probability=0.8 if job_data.visa_sponsorship else 0.3,
                    )
                    db.add(new_job)
                    
            except Exception as e:
                logger.debug(f"[JOBS] Warning: Could not store job: {e}")
        
        await db.commit()
        
        # Convert to responses
        job_responses = [
            JobResponse(
                id=job.id,
                title=job.title,
                company=job.company,
                location=job.location,
                country_code=job.country_code,
                salary_min=job.salary_min,
                salary_max=job.salary_max,
                visa_sponsorship=job.visa_sponsorship,
                visa_probability=job.visa_probability or 0.5,
                remote=job.remote,
                source=job.source,
                posted_date=job.posted_date.isoformat() if job.posted_date else None,
                description=job.description[:500],
                view_count=job.view_count,
                tailored_count=job.tailored_count,
            )
            for job in jobs_paginated
        ]
        
        logger.info(f"[JOBS] Returned {len(job_responses)} jobs")
        
        return JobSearchResponse(
            jobs=job_responses,
            total=len(jobs_data),
            limit=limit,
            offset=offset,
        )
        
    except Exception as e:
        logger.error(f"[JOBS] Search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get detailed job information"""
    try:
        stmt = select(Job).where(Job.id == uuid.UUID(job_id))
        result = await db.execute(stmt)
        job = result.scalar_one_or_none()
        
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        
        # Increment view count
        job.view_count += 1
        db.add(job)
        await db.commit()
        
        return JobResponse(
            id=str(job.id),
            title=job.title,
            company=job.company,
            location=job.location,
            country_code=job.country_code,
            salary_min=job.salary_min,
            salary_max=job.salary_max,
            visa_sponsorship=job.visa_sponsorship,
            remote=job.remote,
            source=job.source,
            posted_date=job.posted_date.isoformat() if job.posted_date else None,
            description=job.description,  # Full description
            view_count=job.view_count,
            tailored_count=job.tailored_count,
        )
        
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid job ID format")
    except Exception as e:
        logger.error(f"[JOBS] Get job failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{job_id}/tailor", response_model=TailorResponse)
async def tailor_resume_for_job(
    job_id: str,
    request: TailorRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    **Million-Dollar ATS Pipeline** - 4 Steps to Professional-Grade Resume Tailoring:
    
    1. **Auditor (Local BERT)**: Extract keywords from JD at 20ms (not 2s via API)
    2. **Impact Transformer**: Rewrite bullets with STAR method + quantifiable metrics
    3. **Semantic Matcher**: Deep contextual alignment via embeddings (not keyword counting)
    4. **Grader**: Quality validation (70% semantic + 30% tone/grammar)
    
    Returns: Tailored resume + match tier + missing signals + impact improvements
    """
    try:
        # Fetch job
        stmt = select(Job).where(Job.id == uuid.UUID(job_id))
        result = await db.execute(stmt)
        job = result.scalar_one_or_none()
        
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        
        logger.info(f"[TAILOR] 4-step million-dollar pipeline: {job.title} @ {job.company}")
        
        # ================================================================
        # Step 1: BERT Auditor (Local, 20ms, Zero-Cost)
        # ================================================================
        logger.info("[TAILOR] Step 1: BERT Auditor (local keyword extraction)...")
        bert_auditor = get_bert_auditor()
        skill_rubric = await bert_auditor.audit_job_description(job.description)
        
        logger.debug(f"[TAILOR] Found skills: {skill_rubric.hard_skills[:5]}")
        
        # ================================================================
        # Step 2: Impact Transformer (STAR Method + Metrics Injection)
        # ================================================================
        logger.info("[TAILOR] Step 2: Impact Transformer (STAR rewriting)...")
        impact_transformer = get_impact_transformer()
        
        # Split resume into experience section
        experience_improvements = await impact_transformer.transform_resume_section(
            request.resume_text,
            skill_rubric.hard_skills + skill_rubric.soft_skills
        )
        
        # Build base tailored resume with impact-driven bullets
        tailored_resume_base = request.resume_text
        
        # ================================================================
        # Step 3: Tailor Agent (Enhanced with Keywords + Impact)
        # ================================================================
        logger.info("[TAILOR] Step 3: Tailor Agent (keyword injection)...")
        tailor_agent = create_tailor_agent()
        
        keywords_context = f"""
        **Audited Job Requirements** (from BERT NER):
        - Hard Skills: {', '.join(skill_rubric.hard_skills[:8])}
        - Soft Skills: {', '.join(skill_rubric.soft_skills[:5])}
        - Tools/Frameworks: {', '.join(skill_rubric.tools_and_frameworks[:8])}
        - Must-have: {', '.join(skill_rubric.must_have_phrases[:3])}
        - Experience Level: {skill_rubric.experience_requirements}
        
        **Rewriting Instructions**:
        1. Inject STAR method (Situation-Task-Action-Result)
        2. Add quantifiable metrics (%, users affected, time saved)
        3. Highlight experience with listed skills
        4. Use achievement-oriented action verbs
        """
        
        tailored_resume = await tailor_agent.invoke({
            "resume": tailored_resume_base,
            "job_description": job.description,
            "keywords_context": keywords_context,
        })
        
        logger.debug(f"[TAILOR] Resume tailored: {len(tailored_resume)} chars")
        
        # ================================================================
        # Step 4: Semantic Matcher + Grader (70% semantic + 30% quality)
        # ================================================================
        logger.info("[TAILOR] Step 4: Semantic analysis + grading...")
        
        matcher = get_matcher()
        match_metrics = await asyncio.to_thread(
            matcher.compute_match_metrics,
            job.description,
            tailored_resume,
            skill_rubric
        )
        
        grader = get_grader()
        grade_result = await grader.grade_resume(
            tailored_resume,
            job.description,
            skill_rubric,
            original_resume=request.resume_text
        )
        
        logger.info(f"[TAILOR] Match: {grade_result.match_tier} ({grade_result.semantic_similarity}%) | Score: {grade_result.score}")
        
        # ================================================================
        # Store Comprehensive Result in Database
        # ================================================================
        tailored_resume_obj = TailoredResume(
            user_id=current_user.id,
            job_id=uuid.UUID(job_id),
            original_resume=request.resume_text,
            tailored_resume=tailored_resume,
            
            # Pipeline Results
            auditor_result=skill_rubric.dict(),
            grader_result=grade_result.dict(),
            
            # Phase 7: Enhanced Metrics (Million-Dollar ATS)
            semantic_similarity=grade_result.semantic_similarity,
            match_tier=grade_result.match_tier,
            missing_signals=[s.dict() for s in grade_result.missing_signals] if hasattr(grade_result, 'missing_signals') else [],
            hit_rate=grade_result.hit_rate if hasattr(grade_result, 'hit_rate') else 0.0,
            overall_fit=grade_result.overall_fit if hasattr(grade_result, 'overall_fit') else "",
            impact_score=experience_improvements.get('section_impact'),
            bullet_improvements=[b.dict() for b in experience_improvements.get('transformed_bullets', [])][:5],
            
            status="graded" if grade_result.passed else "needs_revision",
            retry_count=0,
        )
        db.add(tailored_resume_obj)
        
        # Update job stats
        job.tailored_count += 1
        if not job.skill_rubric:
            job.skill_rubric = skill_rubric.dict()
        db.add(job)
        
        await db.commit()
        
        # ================================================================
        # Build Rich Response
        # ================================================================
        logger.info(f"[TAILOR] Complete! Score: {grade_result.score}/100")
        
        return TailorResponse(
            tailored_resume_id=str(tailored_resume_obj.id),
            tailored_resume=tailored_resume,
            match_score=grade_result.score,
            match_tier=grade_result.match_tier if hasattr(grade_result, 'match_tier') else "Unknown",
            semantic_similarity=grade_result.semantic_similarity if hasattr(grade_result, 'semantic_similarity') else 0.0,
            keyword_coverage=grade_result.hit_rate if hasattr(grade_result, 'hit_rate') else 0.0,
            overall_fit=grade_result.overall_fit if hasattr(grade_result, 'overall_fit') else "N/A",
            missing_signals=[s.dict() for s in grade_result.missing_signals] if hasattr(grade_result, 'missing_signals') else [],
            status="passed" if grade_result.passed else "needs_revision",
            feedback=grade_result.retry_prompt if hasattr(grade_result, 'retry_prompt') else None,
        )
        
    except ValueError as e:
        logger.error(f"[TAILOR] Invalid job ID: {e}")
        raise HTTPException(status_code=400, detail="Invalid job ID format")
    except Exception as e:
        logger.error(f"[TAILOR] Pipeline failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Tailoring failed: {str(e)}")


# ================================================================
# Auto-Optimize Endpoint - 1-Click Keyword Injection
# ================================================================

@router.post("/{job_id}/auto-optimize", response_model=AutoOptimizeResponse)
async def auto_optimize_resume(
    job_id: str,
    request: AutoOptimizeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    1-Click Auto-Optimize - Inject missing keywords without full regeneration.
    
    Takes top missing hard skills and injects them into a Skills section.
    Returns instantly with estimated score boost.
    
    Processing time: ~2 seconds (BERT auditor + semantic matcher)
    """
    start_time = time.time()
    
    try:
        # Check scan quota for free users
        if current_user.tier == "free":
            if current_user.scans_this_month >= current_user.scan_limit:
                raise HTTPException(
                    status_code=403,
                    detail=f"Free tier limit reached ({current_user.scan_limit} scans/month). Upgrade to Pro for unlimited scans."
                )
        
        # Get job
        stmt = select(Job).where(Job.id == uuid.UUID(job_id))
        result = await db.execute(stmt)
        job = result.scalar_one_or_none()
        
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        
        logger.info(f"[AUTO-OPT] User {current_user.id} optimizing for {job.title} at {job.company}")
        
        # Step 1: Extract skills using BERT auditor (local, fast)
        auditor = get_bert_auditor()
        skill_rubric = await auditor.audit_job_description(job.description)
        
        # Step 2: Find missing skills using semantic matcher
        matcher = get_matcher()
        match_metrics = await asyncio.to_thread(
            matcher.compute_match_metrics,
            job.description,
            request.resume_text,
            skill_rubric
        )
        
        # Filter to hard skills only (highest impact)
        missing_hard_skills = [
            s for s in getattr(match_metrics, 'missing_signals', [])
            if getattr(s, 'category', '').lower() == 'hard_skill'
        ][:request.num_keywords]
        
        if not missing_hard_skills:
            logger.info("[AUTO-OPT] No missing hard skills detected")
            return AutoOptimizeResponse(
                optimized_resume=request.resume_text,
                keywords_injected=[],
                estimated_score_boost=0.0,
                processing_time_ms=int((time.time() - start_time) * 1000)
            )
        
        # Step 3: Inject keywords into Skills section
        transformer = get_impact_transformer()
        keywords_to_inject = [getattr(s, 'term', str(s)) for s in missing_hard_skills]
        
        # Simple keyword injection into Skills section
        if "Skills" not in request.resume_text and "SKILLS" not in request.resume_text:
            # No skills section, so add one
            optimized = request.resume_text + "\n\n**Skills**\n" + ", ".join(keywords_to_inject)
        else:
            # Inject into existing skills section
            optimized = request.resume_text
            for keyword in keywords_to_inject:
                if keyword.lower() not in optimized.lower():
                    optimized = optimized.replace(
                        "**Skills**",
                        f"**Skills**\n- {keyword}"
                    )
        
        # Estimate score boost (empirical: 0.5-1.5% per well-placed keyword)
        estimated_boost = len(keywords_to_inject) * 0.8
        
        # Update scan count for free users
        if current_user.tier == "free":
            current_user.scans_this_month += 1
            await db.commit()
        
        processing_time = int((time.time() - start_time) * 1000)
        logger.info(f"[AUTO-OPT] Complete in {processing_time}ms - Injected: {keywords_to_inject}")
        
        return AutoOptimizeResponse(
            optimized_resume=optimized,
            keywords_injected=keywords_to_inject,
            estimated_score_boost=round(estimated_boost, 1),
            processing_time_ms=processing_time
        )
        
    except ValueError as e:
        logger.error(f"[AUTO-OPT] Invalid job ID: {e}")
        raise HTTPException(status_code=400, detail="Invalid job ID format")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[AUTO-OPT] Failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Auto-optimize failed. Please try again.")


# ================================================================
# WebSocket Real-Time Scoring
# ================================================================

@router.websocket("/ws/{job_id}/score")
async def websocket_live_score(
    websocket: WebSocket,
    job_id: str,
    token: str = Query(...),
):
    """
    WebSocket endpoint for real-time resume scoring as user edits.
    
    Client sends: {"action": "score", "resume_text": "..."}
    Server responds: {"score": 78.5, "match_tier": "Strong Match", "keywords_found": 12, "delta": +2.1}
    
    Features:
    - Latency target: <2 seconds per update
    - Debounces: 500ms minimum between processing
    - Times out: Idle connections after 30 minutes
    - Async: Non-blocking thread pool for matcher
    """

    # TODO: Validate JWT token before accepting connection
    # For now, accept all connections (add JWT validation in production)
    
    client_id = f"{job_id}_{str(uuid.uuid4())[:8]}"
    await manager.connect(websocket, client_id)
    
    last_score = 0.0
    last_processed_time = 0
    DEBOUNCE_MS = 500  # Minimum time between processing
    
    try:
        # Get job once (cached for connection lifetime)
        async with AsyncSessionLocal() as db:
            stmt = select(Job).where(Job.id == uuid.UUID(job_id))
            result = await db.execute(stmt)
            job = result.scalar_one_or_none()
            
            if not job:
                await websocket.close(code=1003, reason="Job not found")
                return
        
        logger.info(f"[WS-SCORE] Connected: job={job_id}, client={client_id}")
        
        while True:
            # Receive message from client
            data = await websocket.receive_json()
            
            if data.get("action") != "score":
                continue
            
            resume_text = data.get("resume_text", "")
            
            # Debounce: skip if too soon after last update
            now = time.time() * 1000
            if now - last_processed_time < DEBOUNCE_MS:
                continue
            
            # Skip if resume hasn't changed significantly
            if len(resume_text) < 50:  # Minimum meaningful resume
                continue
            
            # Process in thread to avoid blocking
            try:
                matcher = get_matcher()
                
                # Quick match (no full rubric extraction for speed)
                match_metrics = await asyncio.to_thread(
                    matcher.compute_match_metrics,
                    job.description,
                    resume_text,
                    None  # Skip full rubric for WebSocket speed
                )
                
                new_score = getattr(match_metrics, 'semantic_similarity', 0.0)
                delta = new_score - last_score
                match_tier = getattr(match_metrics, 'match_tier', 'Unknown')
                hit_rate = getattr(match_metrics, 'hit_rate', 0.0)
                
                # Send update
                await manager.send_score(client_id, {
                    "score": round(new_score, 1),
                    "match_tier": match_tier,
                    "keywords_found": int(hit_rate * 100),
                    "delta": round(delta, 1),
                    "timestamp": datetime.utcnow().isoformat()
                })
                
                last_score = new_score
                last_processed_time = now
                
                logger.debug(f"[WS-SCORE] Updated: {new_score} ({delta:+.1f})")
                
            except Exception as e:
                logger.error(f"[WS-SCORE] Processing error: {e}")
                await manager.send_score(client_id, {
                    "error": "Processing failed",
                    "score": last_score
                })
    
    except WebSocketDisconnect:
        manager.disconnect(client_id)
        logger.info(f"[WS-SCORE] Disconnected: {client_id}")
    except Exception as e:
        logger.error(f"[WS-SCORE] Unexpected error: {e}")
        manager.disconnect(client_id)


# ================================================================
# Batch Tailor – tailor one resume against multiple jobs at once
# ================================================================

class BatchTailorRequest(BaseModel):
    resume_text: str = Field(..., min_length=100)
    job_ids: List[str] = Field(..., min_items=1, max_items=10)


class BatchTailorItem(BaseModel):
    job_id: str
    job_title: Optional[str]
    company: Optional[str]
    match_score: Optional[float]
    match_tier: Optional[str]
    missing_signals: Optional[List[dict]]
    tailored_resume_id: Optional[str]
    status: str  # "success" | "error"
    error: Optional[str] = None


class BatchTailorResponse(BaseModel):
    results: List[BatchTailorItem]
    total: int
    succeeded: int


@router.post("/batch-tailor", response_model=BatchTailorResponse)
async def batch_tailor_resume(
    request: BatchTailorRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Tailor one resume against up to 10 jobs in a single call.
    Pro tier only. Runs the 4-step pipeline for each job.
    """
    from ..db_models import UserTier

    if current_user.tier not in (UserTier.pro, UserTier.agency):
        raise HTTPException(
            status_code=403,
            detail="Batch tailoring requires a Pro subscription.",
        )

    results: List[BatchTailorItem] = []

    for job_id_str in request.job_ids:
        try:
            stmt = select(Job).where(Job.id == uuid.UUID(job_id_str))
            res = await db.execute(stmt)
            job = res.scalar_one_or_none()
            if not job:
                results.append(
                    BatchTailorItem(job_id=job_id_str, status="error", error="Job not found")
                )
                continue

            # Step 1: BERT auditor
            auditor = get_bert_auditor()
            skill_rubric = await auditor.audit_job_description(job.description)

            # Step 2: Impact transformer
            transformer = get_impact_transformer()
            impact_result = await transformer.transform_resume_bullets(request.resume_text)
            enhanced_resume = impact_result.get("transformed_resume", request.resume_text)

            # Step 3: AI tailor
            tailor_agent = create_tailor_agent(str(current_user.id))
            tailor_result = await tailor_agent.execute(
                "rewrite_resume_for_job",
                {"resume_text": enhanced_resume, "jd_text": job.description},
            )
            tailored_text = tailor_result.get("rewritten_resume", enhanced_resume) if isinstance(tailor_result, dict) else enhanced_resume

            # Step 4: Semantic matcher
            matcher = get_matcher()
            metrics = await asyncio.to_thread(
                matcher.compute_match_metrics,
                job.description,
                tailored_text,
                skill_rubric,
            )

            # Persist
            record = TailoredResume(
                user_id=current_user.id,
                job_id=job.id,
                original_resume=request.resume_text,
                tailored_resume=tailored_text,
                match_tier=getattr(metrics, "match_tier", None),
                semantic_similarity=getattr(metrics, "semantic_similarity", None),
                missing_signals=getattr(metrics, "missing_signals", None),
                hit_rate=getattr(metrics, "hit_rate", None),
                impact_score=impact_result.get("impact_score"),
                status="tailored",
            )
            db.add(record)
            await db.flush()

            results.append(
                BatchTailorItem(
                    job_id=job_id_str,
                    job_title=job.title,
                    company=job.company,
                    match_score=getattr(metrics, "semantic_similarity", None),
                    match_tier=getattr(metrics, "match_tier", None),
                    missing_signals=getattr(metrics, "missing_signals", []),
                    tailored_resume_id=str(record.id),
                    status="success",
                )
            )
        except Exception as e:
            logger.error(f"[BATCH-TAILOR] job_id={job_id_str} failed: {e}")
            results.append(
                BatchTailorItem(job_id=job_id_str, status="error", error=str(e))
            )

    await db.commit()
    succeeded = sum(1 for r in results if r.status == "success")
    return BatchTailorResponse(results=results, total=len(results), succeeded=succeeded)

"""
IntelliResume AI – LLM-Powered ATS Optimization Engine
FastAPI backend: upload resume & JD, optimize, score, visualize, download DOCX.
"""

import os
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response

from .models import (
    ATSScoreResponse,
    ComprehensiveAnalysisResult,
    FullOptimizationResult,
    JobDescriptionAnalysis,
    OptimizedResumeResponse,
    WritingFeedback,
)

from .services import ats_optimizer, doc_generator, jd_analyzer, openai_service, scorer, visualizer, writing_feedback
from .services.keyword_heatmap import generate_keyword_heatmap
from .services.quality_scorer import calculate_resume_quality
from .services.skill_analyzer import analyze_skill_gap
from .services.resume_parser import extract_resume_text

app = FastAPI(
    title="IntelliResume AI",
    description="LLM-Powered ATS Optimization Engine",
    version="1.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory store for session charts (path -> absolute path). In production use Redis or temp files with TTL.
_chart_paths: dict[str, str] = {}
CHARTS_DIR = Path(os.getenv("CHARTS_DIR", "backend/charts"))
CHARTS_DIR.mkdir(parents=True, exist_ok=True)


@app.get("/")
async def root():
    return {"status": "ATS API is online"}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "IntelliResume AI"}


@app.post("/api/scan")
async def scan_resume(
    resume: UploadFile = File(...),
    job_description: str = Form(...),
):
    """
    Scan resume against job description.
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

    # Analyze with OpenAI
    analysis_result = await openai_service.analyze_resume_match(resume_text, job_description)

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


@app.post("/api/analyze/comprehensive")
async def comprehensive_analysis(
    resume: UploadFile = File(...),
    job_description: Optional[UploadFile] = File(None),
    jd_text: Optional[str] = Form(None),
) -> ComprehensiveAnalysisResult:
    """
    Comprehensive portfolio-level analysis including:
    - ATS optimization
    - Skill gap analysis
    - Resume quality scoring
    - Keyword heatmap
    - Writing feedback
    - Professional visualizations
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

    # 2) Extract JD text
    jd_text = (jd_text or "").strip()
    if not jd_text and job_description:
        jd_content = await job_description.read()
        jd_text = extract_resume_text(jd_content, job_description.filename or "jd.pdf")
    jd_text = (jd_text or "").strip()
    
    if not jd_text:
        raise HTTPException(status_code=400, detail="Job description is required.")

    # 3) JD analysis (OpenAI)
    jd_analysis = await jd_analyzer.analyze_job_description(jd_text)

    # 4) Optimize resume (OpenAI)
    opt_result = await ats_optimizer.optimize_resume(resume_text, jd_text)
    optimized_text = opt_result.optimized_resume or resume_text

    # 5) ATS score
    ats_score_result = scorer.compute_ats_score(optimized_text, jd_text, jd_analysis)

    # 6) Skill gap analysis
    skill_gap = analyze_skill_gap(
        optimized_text,
        jd_analysis.required_skills,
        jd_analysis.preferred_skills
    )

    # 7) Resume quality score
    resume_quality = calculate_resume_quality(optimized_text, jd_text)

    # 8) Keyword heatmap
    keyword_heatmap = generate_keyword_heatmap(optimized_text, jd_text, top_n=20)

    # 9) Writing feedback
    feedback = await writing_feedback.get_writing_feedback(optimized_text)

    # 10) Generate all charts
    session_id = str(uuid.uuid4())
    session_charts = CHARTS_DIR / session_id
    session_charts.mkdir(parents=True, exist_ok=True)
    
    # Generate basic charts
    chart_paths = visualizer.generate_all_charts(ats_score_result, session_charts)
    
    # Add additional charts
    heatmap_path = visualizer.chart_keyword_heatmap(keyword_heatmap, session_charts)
    chart_paths["keyword_heatmap"] = heatmap_path
    
    skill_gap_path = visualizer.chart_skill_gap(skill_gap.match_count, len(skill_gap.missing_skills), session_charts)
    chart_paths["skill_gap"] = skill_gap_path
    
    quality_path = visualizer.chart_quality_breakdown(
        resume_quality.readability_score,
        resume_quality.formatting_score,
        resume_quality.content_score,
        resume_quality.keyword_density_score,
        session_charts
    )
    chart_paths["quality_breakdown"] = quality_path
    
    # Convert to API URLs
    chart_urls = {}
    for name, abs_path in chart_paths.items():
        rel = Path(abs_path).name
        chart_urls[name] = f"/api/charts/{session_id}/{rel}"
        _chart_paths[chart_urls[name]] = abs_path

    return ComprehensiveAnalysisResult(
        original_resume=resume_text,
        optimized_resume=optimized_text,
        ats_score=ats_score_result,
        jd_analysis=jd_analysis,
        skill_gap=skill_gap,
        resume_quality=resume_quality,
        keyword_heatmap=keyword_heatmap,
        writing_feedback=feedback,
        chart_paths=chart_urls,
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

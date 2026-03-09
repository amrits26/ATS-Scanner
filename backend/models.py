"""Pydantic models for API requests and responses."""

from typing import Any

from pydantic import BaseModel, Field


# --- Job Description Analyzer ---
class JobDescriptionAnalysis(BaseModel):
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    experience_level: str = ""


# --- ATS Optimizer ---
class SectionImprovements(BaseModel):
    summary: str = ""
    experience: str = ""
    skills: str = ""


class OptimizedResumeResponse(BaseModel):
    optimized_resume: str = ""
    section_improvements: SectionImprovements = Field(default_factory=SectionImprovements)


# --- ATS Scorer ---
class ATSScoreResponse(BaseModel):
    keyword_match_percent: float = 0.0
    semantic_similarity_score: float = 0.0
    final_ats_score: float = 0.0
    missing_keywords: list[str] = Field(default_factory=list)
    recommended_keywords_to_add: list[str] = Field(default_factory=list)


# --- Bonus: weak verbs, metrics, passive ---
class WritingFeedback(BaseModel):
    weak_verbs_detected: list[str] = Field(default_factory=list)
    bullets_without_metrics: list[str] = Field(default_factory=list)
    passive_voice_phrases: list[str] = Field(default_factory=list)
    readability_score: float = 0.0
    sections_detected: list[str] = Field(default_factory=list)


# --- Full optimization result ---
class FullOptimizationResult(BaseModel):
    optimized_resume: str = ""
    section_improvements: SectionImprovements = Field(default_factory=SectionImprovements)
    ats_score: ATSScoreResponse = Field(default_factory=ATSScoreResponse)
    jd_analysis: JobDescriptionAnalysis = Field(default_factory=JobDescriptionAnalysis)
    writing_feedback: WritingFeedback | None = None
    chart_paths: dict[str, str] = Field(default_factory=dict)


# --- Skill Gap Analysis ---
class SkillGapAnalysis(BaseModel):
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    gap_score: float = 0.0  # 0-100, percentage of skills matched
    match_count: int = 0
    total_required: int = 0


# --- Resume Quality Score ---
class ResumeQualityScore(BaseModel):
    overall_score: float = 0.0  # 0-100
    readability_score: float = 0.0
    formatting_score: float = 0.0
    content_score: float = 0.0
    keyword_density_score: float = 0.0
    feedback: list[str] = Field(default_factory=list)


# --- Keyword Heatmap ---
class KeywordHeatmapData(BaseModel):
    keywords: list[str] = Field(default_factory=list)
    frequencies: list[int] = Field(default_factory=list)
    importance_scores: list[float] = Field(default_factory=list)  # 0-1 scale


# --- Comprehensive Analysis Result ---
class ComprehensiveAnalysisResult(BaseModel):
    original_resume: str = ""
    optimized_resume: str = ""
    ats_score: ATSScoreResponse = Field(default_factory=ATSScoreResponse)
    jd_analysis: JobDescriptionAnalysis = Field(default_factory=JobDescriptionAnalysis)
    skill_gap: SkillGapAnalysis = Field(default_factory=SkillGapAnalysis)
    resume_quality: ResumeQualityScore = Field(default_factory=ResumeQualityScore)
    keyword_heatmap: KeywordHeatmapData = Field(default_factory=KeywordHeatmapData)
    writing_feedback: WritingFeedback | None = None
    chart_paths: dict[str, str] = Field(default_factory=dict)

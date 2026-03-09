"""Skill gap analysis between resume and job description."""

from ..models import SkillGapAnalysis
from ..utils.text_cleaner import extract_words, normalize_for_ats


def analyze_skill_gap(
    resume_text: str,
    required_skills: list[str],
    preferred_skills: list[str],
) -> SkillGapAnalysis:
    """
    Analyze skill gaps between resume and JD requirements.
    Returns matched skills, missing skills, and gap score.
    """
    resume_text_norm = normalize_for_ats(resume_text or "")
    resume_words = set(extract_words(resume_text))
    
    # Extract skill tokens from required and preferred
    required_tokens = set()
    matched_required = []
    missing_required = []
    
    for skill in required_skills:
        skill_norm = normalize_for_ats(skill)
        skill_words = set(extract_words(skill_norm))
        required_tokens.update(skill_words)
        
        # Check if skill is mentioned in resume (simple keyword matching)
        if skill_words and any(word in resume_words for word in skill_words):
            matched_required.append(skill)
        else:
            missing_required.append(skill)
    
    # Do the same for preferred skills
    preferred_tokens = set()
    matched_preferred = []
    missing_preferred = []
    
    for skill in preferred_skills:
        skill_norm = normalize_for_ats(skill)
        skill_words = set(extract_words(skill_norm))
        preferred_tokens.update(skill_words)
        
        if skill_words and any(word in resume_words for word in skill_words):
            matched_preferred.append(skill)
        else:
            missing_preferred.append(skill)
    
    # Calculate gap score (weighted: required > preferred)
    total_required = len(required_skills) if required_skills else 1
    matched_count = len(matched_required)
    
    # Weight: 70% required, 30% preferred
    if required_skills:
        required_match = matched_count / len(required_skills) if required_skills else 0
    else:
        required_match = 0
    
    if preferred_skills:
        preferred_match = len(matched_preferred) / len(preferred_skills) if preferred_skills else 0
    else:
        preferred_match = 0
    
    gap_score = round((required_match * 0.7 + preferred_match * 0.3) * 100, 1)
    
    return SkillGapAnalysis(
        matched_skills=matched_required + matched_preferred,
        missing_skills=missing_required + missing_preferred,
        gap_score=min(100.0, max(0.0, gap_score)),
        match_count=len(matched_required) + len(matched_preferred),
        total_required=total_required + len(preferred_skills),
    )

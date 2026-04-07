"""Skill gap analysis between resume and job description with semantic categorization."""

from difflib import SequenceMatcher
from ..models import SkillGapAnalysis, SkillGap
from ..utils.text_cleaner import extract_words, normalize_for_ats


def _fuzzy_skill_match(skill: str, resume_text: str, threshold: float = 0.75) -> bool:
    """
    Fuzzy match skill against resume text to handle variations.
    Examples: "Power BI" matches "powerbi", "C++" matches "cpp" or "c plus plus"
    Returns True if similarity >= threshold
    """
    skill_norm = normalize_for_ats(skill).lower()
    resume_norm = normalize_for_ats(resume_text).lower()
    
    if not skill_norm or not resume_norm:
        return False
    
    # Exact substring match (fast path)
    if skill_norm in resume_norm:
        return True
    
    # Get tokens from skill and check each against resume
    skill_tokens = extract_words(skill_norm)
    resume_tokens = set(extract_words(resume_norm))
    
    # If any primary token (first word of skill) is in resume, do fuzzy match
    if skill_tokens:
        primary_token = skill_tokens[0]
        
        # Look for similar tokens in resume
        for resume_token in resume_tokens:
            # Base similarity between tokens
            similarity = SequenceMatcher(None, primary_token, resume_token).ratio()
            if similarity >= threshold:
                return True
    
    # Full fuzzy match: compare entire skill against resume words
    # This catches cases like "node.js" vs "nodejs"
    for resume_token in resume_tokens:
        similarity = SequenceMatcher(None, skill_norm, resume_token).ratio()
        if similarity >= threshold:
            return True
    
    return False


# Hard skills (technical) - commonly required in tech roles
HARD_SKILL_KEYWORDS = {
    "python", "java", "javascript", "typescript", "csharp", "c++", "c#", "ruby", "go", "rust", "php", "sql", "nosql",
    "aws", "azure", "gcp", "docker", "kubernetes", "jenkins", "git", "linux", "windows", "api", "rest", "graphql",
    "react", "angular", "vue.js", "node.js", "fastapi", "django", "spring", "express", "flask", "machine learning",
    "ai", "deep learning", "nlp", "tensorflow", "pytorch", "scikit-learn", "pandas", "numpy", "spark", "hadoop",
    "mongodb", "postgresql", "mysql", "redis", "elasticsearch", "kafka", "rabitmq", "microservices", "devops"
}

# Soft skills (interpersonal/management)
SOFT_SKILL_KEYWORDS = {
    "communication", "leadership", "teamwork", "collaboration", "problem-solving", "critical thinking",
    "time management", "project management", "agile", "scrum", "mentoring", "coaching", "negotiation",
    "presentation", "interpersonal", "emotional intelligence", "adaptability", "creativity", "innovation"
}

# Skills that overlap or are transferable
ADJACENT_SKILL_KEYWORDS = {
    "sql": ["nosql", "database", "data management"],
    "python": ["ruby", "javascript", "php"],
    "java": ["c++", "csharp", "golang"],
    "aws": ["azure", "gcp", "cloud"],
    "react": ["angular", "vue.js"],
    "linux": ["windows", "unix"],
}


def _categorize_skill(skill: str) -> str:
    """Determine if a skill is hard, soft, or neutral."""
    skill_lower = skill.lower()
    
    if any(keyword in skill_lower for keyword in HARD_SKILL_KEYWORDS):
        return "hard_gap"
    elif any(keyword in skill_lower for keyword in SOFT_SKILL_KEYWORDS):
        return "soft_gap"
    else:
        return "hard_gap"  # Default: treat as hard skill


def _calculate_relevance_score(skill: str, all_missing: list[str], is_required: bool = False) -> float:
    """
    Calculate relevance score (1-10) based on:
    - Required vs Preferred (required skills worth more)
    - Frequency in skill list
    - Position in skill list (earlier = more important)
    """
    base_score = 7.0 if is_required else 5.0
    
    # Adjust by position (earlier in list = higher priority)
    position_penalty = 0.0
    try:
        position = all_missing.index(skill)
        position_penalty = min(3.0, position * 0.2)  # Penalty increases with position
    except ValueError:
        pass
    
    relevance = round(min(10.0, max(1.0, base_score - position_penalty)), 1)
    return relevance


def _find_adjacent_skills(missing_skill: str, matched_skills: list[str]) -> list[str]:
    """Find matched skills that are adjacent/transferable to the missing skill."""
    adjacent = []
    skill_lower = missing_skill.lower()
    
    for matched in matched_skills:
        matched_lower = matched.lower()
        
        # Check if they're in same category
        for base_skill, similar_skills in ADJACENT_SKILL_KEYWORDS.items():
            if base_skill in skill_lower or base_skill in matched_lower:
                for similar in similar_skills:
                    if similar in skill_lower and base_skill in matched_lower:
                        adjacent.append(matched)
                        break
    
    return adjacent


def _generate_recommendation(skill: str, category: str, adjacent_skills: list[str]) -> str:
    """Generate actionable recommendation to bridge the skill gap."""
    if adjacent_skills:
        adjacent_str = ", ".join(adjacent_skills[:2])
        return f"Highlight {adjacent_str} to show transferable experience in {skill}"
    
    if category == "hard_gap":
        return f"Take an online course or build a project using {skill} to demonstrate competency"
    elif category == "soft_gap":
        return f"Provide examples in your resume/interview demonstrating {skill}"
    else:
        return f"Consider gaining experience or certification in {skill}"


def analyze_skill_gap(
    resume_text: str,
    required_skills: list[str],
    preferred_skills: list[str],
) -> SkillGapAnalysis:
    """
    Semantic Skill Gap Analysis with categorization and recommendations.
    
    - Categorizes missing skills into Hard Gaps (technical), Soft Gaps (interpersonal), and Adjacent Skills
    - Assigns relevance_score (1-10) based on importance and frequency
    - Generates actionable recommendations
    - Identifies top 5 critical gaps
    """
    resume_text_norm = normalize_for_ats(resume_text or "")
    resume_words = set(extract_words(resume_text))
    
    # Track matched and missing
    matched_required = []
    missing_required = []
    matched_preferred = []
    missing_preferred = []
    
    # Process required skills
    for skill in required_skills:
        if _fuzzy_skill_match(skill, resume_text):
            matched_required.append(skill)
        else:
            missing_required.append(skill)
    
    # Process preferred skills
    for skill in preferred_skills:
        if _fuzzy_skill_match(skill, resume_text):
            matched_preferred.append(skill)
        else:
            missing_preferred.append(skill)
    
    all_matched = matched_required + matched_preferred
    all_missing = missing_required + missing_preferred
    
    # Categorize missing skills and generate recommendations
    hard_gaps = []
    soft_gaps = []
    adjacent_skills = []
    
    for skill in all_missing:
        category = _categorize_skill(skill)
        relevance = _calculate_relevance_score(skill, all_missing, skill in missing_required)
        adjacent = _find_adjacent_skills(skill, all_matched)
        recommendation = _generate_recommendation(skill, category, adjacent)
        
        gap_item = SkillGap(
            skill=skill,
            category=category,
            relevance_score=relevance,
            recommendation=recommendation
        )
        
        if adjacent:
            adjacent_skills.append(gap_item)
        elif category == "hard_gap":
            hard_gaps.append(gap_item)
        else:
            soft_gaps.append(gap_item)
    
    # Sort by relevance score and identify top 5 critical gaps
    all_gaps = hard_gaps + soft_gaps + adjacent_skills
    all_gaps.sort(key=lambda x: x.relevance_score, reverse=True)
    critical_gaps = all_gaps[:5]
    
    # Calculate gap score (weighted: required > preferred)
    total_required = len(required_skills) if required_skills else 1
    matched_count = len(matched_required)
    
    required_match = matched_count / len(required_skills) if required_skills else 0
    preferred_match = len(matched_preferred) / len(preferred_skills) if preferred_skills else 0
    
    gap_score = round((required_match * 0.7 + preferred_match * 0.3) * 100, 1)
    
    return SkillGapAnalysis(
        matched_skills=all_matched,
        missing_skills=all_missing,
        hard_gaps=hard_gaps,
        soft_gaps=soft_gaps,
        adjacent_skills=adjacent_skills,
        critical_gaps=critical_gaps,
        gap_score=min(100.0, max(0.0, gap_score)),
        match_count=len(all_matched),
        total_required=total_required + len(preferred_skills),
    )

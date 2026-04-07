"""Job description analyzer using Google Gemini to extract structured ATS-relevant data."""

import json
import os
import re
from typing import Any

import google.generativeai as genai
from dotenv import load_dotenv

from ..models import JobDescriptionAnalysis
from ..utils.text_cleaner import clean_extracted_text

# Load environment variables and configure Gemini
load_dotenv()
api_key = os.getenv("GOOGLE_API_KEY")
if api_key:
    genai.configure(api_key=api_key)


SYSTEM_JD = """You are an expert ATS (Applicant Tracking System) analyst. Your task is to extract structured data from job descriptions for resume optimization.
Return STRICT JSON only. No explanations. Do not fabricate experience or add content not present in the job description.
Output must be valid JSON with these exact keys: required_skills, preferred_skills, responsibilities, keywords, tools, experience_level.
Use empty arrays or empty string when a field is not found."""

USER_JD_TEMPLATE = """Extract ATS-relevant data from this job description. Return STRICT JSON only.

Job description:
---
{jd_text}
---

Return a single JSON object with:
- required_skills: list of required skills (exact phrases from JD)
- preferred_skills: list of preferred/nice-to-have skills
- responsibilities: list of key responsibilities
- keywords: list of important keywords for ATS (technical terms, tools, methodologies)
- tools: list of software/tools mentioned
- experience_level: e.g. "Entry", "Mid", "Senior", "Lead", or ""

Do not fabricate. Use only what is stated. Return STRICT JSON only. No markdown, no code block wrapper."""


async def analyze_job_description(jd_text: str) -> JobDescriptionAnalysis:
    """Call Google Gemini to extract structured JD data. Handles empty/short text and JSON errors."""
    cleaned = clean_extracted_text(jd_text)
    if len(cleaned) < 20:
        return JobDescriptionAnalysis(
            experience_level="",
        )

    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        # Fallback: Manual extraction when no API key
        required_skills, preferred_skills = _extract_skills_fallback(jd_text)
        keywords = _extract_keywords_fallback(jd_text)
        print(f"[JD_ANALYZER] No API key, using fallback: {len(required_skills)} required skills")
        return JobDescriptionAnalysis(
            required_skills=required_skills,
            preferred_skills=preferred_skills,
            keywords=keywords,
            experience_level="",
        )

    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = SYSTEM_JD + "\n\n" + USER_JD_TEMPLATE.format(jd_text=cleaned[:12000])
        resp = model.generate_content(prompt)
        content = (resp.text or "").strip()
        content = _strip_json_block(content)
        data: dict[str, Any] = json.loads(content)
        return JobDescriptionAnalysis(
            required_skills=_list(data.get("required_skills")),
            preferred_skills=_list(data.get("preferred_skills")),
            responsibilities=_list(data.get("responsibilities")),
            keywords=_list(data.get("keywords")),
            tools=_list(data.get("tools")),
            experience_level=str(data.get("experience_level") or "").strip(),
        )
    except Exception as e:
        # Fallback: Manual extraction when Gemini fails
        required_skills, preferred_skills = _extract_skills_fallback(jd_text)
        keywords = _extract_keywords_fallback(jd_text)
        print(f"[JD_ANALYZER] Gemini failed ({type(e).__name__}), using fallback: {len(required_skills)} required skills")
        return JobDescriptionAnalysis(
            required_skills=required_skills,
            preferred_skills=preferred_skills,
            keywords=keywords,
            experience_level="",
        )


# ============================================================================
# Keyword Sanitization Filters
# ============================================================================

# Stop words and garbage tokens to filter out from skill extraction
STOP_WORDS = {
    # Articles and prepositions
    "the", "a", "an", "and", "or", "is", "are", "was", "were", "be", "been",
    "have", "has", "had", "do", "does", "did", "will", "would", "should", "could",
    "may", "might", "must", "can", "for", "of", "in", "on", "at", "to", "by",
    "as", "with", "from", "up", "about", "into", "through", "out", "that",
    "this", "which", "who", "what", "where", "when", "why", "how",
    # Common verbs
    "get", "got", "make", "made", "come", "came", "see", "saw", "go", "went",
    "know", "knew", "take", "took", "think", "thought", "use", "used",
    # Common adjectives
    "all", "any", "each", "every", "both", "few", "more", "most", "other",
    "some", "such", "no", "nor", "not", "own", "same", "than", "too",
    "very", "just", "only", "also", "while", "again", "over", "well", "good",
    "able", "new", "old", "right", "real", "best", "first", "last", "long",
    # Pronouns
    "he", "she", "it", "we", "they", "you", "i", "me", "him", "her", "us",
    "them", "my", "your", "his", "its", "our", "their",
    # HTTP/API/Junk/Status codes
    "http", "https", "rest", "json", "xml", "401", "403", "404", "500", "200",
    # Resume template garbage
    "ability", "actionable", "actively", "activity", "acumen", "adapt",
    "work", "worked", "working", "job", "jobs", "role", "roles",
    "responsibility", "responsible", "respond", "response",
    "business", "company", "organization", "department", "team", "group",
    "project", "process", "implementation", "experience", "involved",
    "managed", "collaborated", "contributed", "asap", "basis", "etc",
    "key", "strong", "knowledge", "skill", "background", "prefer", "preferred",
    "yet", "well", "own", "other", "database", "software", "system",
    "application", "web", "mobile", "amp", "nbsp",
    "0", "1", "2", "3", "4", "5", "6", "7", "8", "9",
}

def _is_valid_skill_token(token: str) -> bool:
    """Validate that a token is a legitimate skill keyword (not garbage noise like '2', '6hr', 'asap')."""
    if not token or len(token.strip()) < 3:
        return False
    
    token_clean = token.strip().lower()
    
    # Reject common stop words
    if token_clean in STOP_WORDS:
        return False
    
    # Reject if >50% digits (e.g., "2", "6hr", "24/7")
    if any(c.isdigit() for c in token_clean):
        digit_ratio = sum(1 for c in token_clean if c.isdigit()) / len(token_clean)
        if digit_ratio > 0.5:
            return False
    
    # Reject if mostly special characters (but allow C++, C#, +, /)
    special_count = sum(1 for c in token_clean if not c.isalnum() and c not in {'-', '/', '+', '#'})
    special_ratio = special_count / len(token_clean) if token_clean else 0
    if special_ratio > 0.4:
        return False
    
    # Reject abbreviations that are too short (but allow known technical acronyms)
    known_acronyms = {"c++", "c#", "qa", "ml", "ai", "ui", "ux", "api", "aws", "gcp", "dba", "sql", "csv", "rpa"}
    if len(token_clean) <= 2 and token_clean not in known_acronyms:
        return False
    
    return True


def _extract_skills_fallback(jd_text: str) -> tuple[list[str], list[str]]:
    """
    Fallback skill extraction when Gemini fails.
    Parses JD text to find required and preferred skills.
    """
    text_lower = jd_text.lower()
    required_skills = []
    preferred_skills = []
    
    tech_skills = [
        "python", "java", "javascript", "typescript", "go", "rust", "php", "kotlin",
        "c++", "c#", "ruby", "scala", "swift", "bash", "sql", "nosql",
        "react", "angular", "vue", "svelte", "next.js", "node.js", "express",
        "fastapi", "django", "flask", "spring", "spring boot", "rails", "laravel",
        "postgresql", "mysql", "mongodb", "redis", "elasticsearch", "cassandra",
        "docker", "kubernetes", "aws", "gcp", "azure", "cloud", "terraform",
        "git", "jenkins", "gitlab", "github", "circleci", "ci/cd",
        "machine learning", "tensorflow", "pytorch", "sklearn", "pandas", "numpy",
        "spark", "hadoop", "kafka", "celery", "arq", "rabbitmq", "redis",
        "graphql", "rest api", "microservices", "devops", "linux",
    ]
    
    # Find section markers
    req_idx = text_lower.find('requirement') if 'requirement' in text_lower else text_lower.find('must have') if 'must' in text_lower else 0
    pref_idx = text_lower.find('preferred') if 'preferred' in text_lower else text_lower.find('nice to have') if 'nice' in text_lower else -1
    
    # Split sections
    required_section = text_lower[req_idx:pref_idx] if pref_idx > req_idx else text_lower[req_idx:]
    preferred_section = text_lower[pref_idx:] if pref_idx > 0 else ""
    
    # Extract skills from each section
    for skill in tech_skills:
        if skill in required_section and skill not in required_skills:
            required_skills.append(skill)
        if skill in preferred_section and skill not in preferred_skills:
            preferred_skills.append(skill)
    
    return required_skills, preferred_skills


def _extract_keywords_fallback(jd_text: str) -> list[str]:
    """Extract keywords from JD when Gemini fails."""
    text_lower = jd_text.lower()
    words = re.findall(r'\b[a-z0-9+#_-]+\b', text_lower)
    
    keywords = []
    for word in words:
        if len(word) >= 3 and word not in STOP_WORDS and word not in keywords:
            keywords.append(word)
    
    return keywords[:30]


def _list(val: Any) -> list[str]:
    if not isinstance(val, list):
        return []
    return [str(x).strip() for x in val if x and _is_valid_skill_token(x)]


def _strip_json_block(text: str) -> str:
    """Remove markdown code block if present."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```\s*$", "", text)
    return text.strip()

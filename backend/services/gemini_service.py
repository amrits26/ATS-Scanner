"""Google Gemini service for ATS analysis."""

import json
import os
import re
from typing import Any, Dict, List

import google.generativeai as genai
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    raise ValueError("GOOGLE_API_KEY not found in environment variables")

genai.configure(api_key=api_key)


# ---------------------------------------------------------------------------
# Consolidated single-call prompt — JD analysis, resume optimisation,
# skill-gap, ATS scoring, and executive summary in one Gemini round-trip.
# ---------------------------------------------------------------------------

_CONSOLIDATED_PROMPT = """\
You are an expert ATS (Applicant Tracking System) optimization engine and professional resume writer.
Analyze the job description and the candidate's resume below, then return a single JSON object.

RULES:
1. **Job Description Analysis**
   - Extract: required_skills, preferred_skills, keywords, tools_and_technologies, experience_level.
   - Do NOT invent skills not present in the JD.

2. **Resume Optimization**
   - Rewrite bullet points with strong action verbs (Spearheaded, Engineered, Accelerated …).
   - Preserve ALL factual information — do NOT fabricate experience, skills, or metrics.
   - Clarify existing metrics; eliminate passive voice and filler phrases.
   - Keep the original section structure (Summary, Experience, Education, Skills, etc.).

3. **Skill Gap Analysis**
   - Compare resume skills with JD required_skills.
   - Treat common variations as equivalent (React.js ≈ React, AWS ≈ Amazon Web Services).
   - gap_score = (matched / total_required) * 100.

4. **ATS Score Calculation**
   - keyword_match_percent: % of JD keywords found in the resume (0-100).
   - semantic_similarity_score: contextual alignment (0.0-1.0).
   - final_ats_score: 55 % keyword_match + 45 % semantic_similarity, scaled to 0-100.
   - List missing_keywords and recommended_keywords_to_add (only if they can be added truthfully).

5. **Executive Summary**
   - 3-5 sentences for a non-technical hiring manager.
   - Highlight strongest matches, critical gaps, and one impactful next step.

Return ONLY valid JSON — no markdown fences, no commentary outside the object.

{
  "jd_analysis": {
    "required_skills": [],
    "preferred_skills": [],
    "keywords": [],
    "tools_and_technologies": [],
    "experience_level": ""
  },
  "optimized_resume": "",
  "skill_gap": {
    "matched_skills": [],
    "missing_skills": [],
    "gap_score": 0.0
  },
  "ats_score": {
    "keyword_match_percent": 0,
    "semantic_similarity_score": 0.0,
    "final_ats_score": 0,
    "missing_keywords": [],
    "recommended_keywords_to_add": []
  },
  "executive_summary": ""
}

JOB DESCRIPTION:
{job_description}

RESUME:
{resume_text}
"""

# Required top-level keys for response validation
_REQUIRED_KEYS = {"jd_analysis", "optimized_resume", "skill_gap", "ats_score", "executive_summary"}


def _strip_json_fences(text: str) -> str:
    """Remove optional ```json … ``` fences from LLM output."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```\s*$", "", text)
    return text.strip()


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _validate_consolidated(data: dict) -> dict:
    """Validate and normalise the consolidated response, filling safe defaults."""
    # -- jd_analysis --
    jd = data.get("jd_analysis") or {}
    for list_key in ("required_skills", "preferred_skills", "keywords", "tools_and_technologies"):
        if not isinstance(jd.get(list_key), list):
            jd[list_key] = []
    jd.setdefault("experience_level", "")
    data["jd_analysis"] = jd

    # -- optimized_resume --
    if not isinstance(data.get("optimized_resume"), str) or len(data["optimized_resume"].strip()) < 30:
        raise ValueError("optimized_resume is missing or too short")

    # -- skill_gap --
    sg = data.get("skill_gap") or {}
    for list_key in ("matched_skills", "missing_skills"):
        if not isinstance(sg.get(list_key), list):
            sg[list_key] = []
    sg["gap_score"] = _clamp(float(sg.get("gap_score", 0)), 0, 100)
    data["skill_gap"] = sg

    # -- ats_score --
    ats = data.get("ats_score") or {}
    ats["keyword_match_percent"] = _clamp(float(ats.get("keyword_match_percent", 0)), 0, 100)
    ats["semantic_similarity_score"] = _clamp(float(ats.get("semantic_similarity_score", 0)), 0, 1)
    ats["final_ats_score"] = _clamp(float(ats.get("final_ats_score", 0)), 0, 100)
    for list_key in ("missing_keywords", "recommended_keywords_to_add"):
        if not isinstance(ats.get(list_key), list):
            ats[list_key] = []
    data["ats_score"] = ats

    # -- executive_summary --
    if not isinstance(data.get("executive_summary"), str):
        data["executive_summary"] = ""

    return data


def _build_fallback(resume_text: str, job_description: str) -> dict:
    """Return a safe template-based fallback when JSON parsing fails."""
    return {
        "jd_analysis": {
            "required_skills": [],
            "preferred_skills": [],
            "keywords": [],
            "tools_and_technologies": [],
            "experience_level": "",
        },
        "optimized_resume": resume_text,
        "skill_gap": {
            "matched_skills": [],
            "missing_skills": [],
            "gap_score": 0.0,
        },
        "ats_score": {
            "keyword_match_percent": 0,
            "semantic_similarity_score": 0.0,
            "final_ats_score": 0,
            "missing_keywords": [],
            "recommended_keywords_to_add": [],
        },
        "executive_summary": "Analysis could not be completed. Please try again.",
    }


async def analyze_comprehensive(
    resume_text: str,
    job_description: str,
    *,
    model_name: str = "gemini-1.5-flash",
    temperature: float = 0.4,
) -> Dict[str, Any]:
    """
    Single-call comprehensive analysis: JD parsing, resume optimisation,
    skill-gap, ATS scoring, and executive summary in one Gemini round-trip.

    Returns a validated dict matching the consolidated JSON schema.
    Falls back to a safe template on any failure.
    """
    prompt = _CONSOLIDATED_PROMPT.format(
        job_description=job_description[:8000],
        resume_text=resume_text[:12000],
    )

    try:
        model = genai.GenerativeModel(
            model_name,
            generation_config={
                "temperature": temperature,
                "response_mime_type": "application/json",
            },
        )
        response = model.generate_content(prompt)
        content = _strip_json_fences((response.text or "").strip())
        data: dict = json.loads(content)

        missing = _REQUIRED_KEYS - set(data.keys())
        if missing:
            raise ValueError(f"Response missing required keys: {missing}")

        return _validate_consolidated(data)

    except (json.JSONDecodeError, ValueError, TypeError, KeyError) as exc:
        print(f"[GEMINI] Consolidated call failed validation: {exc}")
        return _build_fallback(resume_text, job_description)
    except Exception as exc:
        print(f"[GEMINI] Consolidated call error: {exc}")
        return _build_fallback(resume_text, job_description)


async def analyze_resume_match(resume_text: str, job_description: str) -> Dict:
    """
    Analyze resume against job description using Google Gemini.

    Returns:
        dict with keys: score (int 0-100), missing_skills (list), advice (str)
    """
    prompt = f"""You are an expert ATS (Applicant Tracking System) analyst. Analyze the provided resume against the job description.

Resume:
{resume_text}

Job Description:
{job_description}

Provide a JSON response with exactly these keys:
- score: An integer from 0 to 100 representing overall match percentage
- missing_skills: A list of important skills or keywords from the job description that are missing from the resume
- advice: A brief paragraph of feedback on how well the resume matches the job requirements

Return only valid JSON, no additional text."""

    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(prompt)
        content = response.text.strip()
        result = json.loads(content)

        # Validate structure
        if not all(key in result for key in ["score", "missing_skills", "advice"]):
            raise ValueError("Invalid response structure")

        # Ensure score is int 0-100
        result["score"] = max(0, min(100, int(result["score"])))

        # Ensure missing_skills is list
        if not isinstance(result["missing_skills"], list):
            result["missing_skills"] = []

        # Ensure advice is string
        if not isinstance(result["advice"], str):
            result["advice"] = "Advice not available."

        return result

    except Exception as e:
        # Fallback in case of error
        return {
            "score": 0,
            "missing_skills": [],
            "advice": f"Error during analysis: {str(e)}"
        }

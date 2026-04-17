"""
Auditor Service - Extract keyword rubric from Job Description

Used by the Tailor Agent to identify:
- Hard skills (Kotlin, Python, etc.)
- Soft skills (Leadership, Communication)
- Must-have phrases and tools
- Salary range and requirements
"""

import json
import logging
import os
from typing import Optional
import google.generativeai as genai
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Configure Gemini
genai.configure(api_key=os.getenv("GEMINI_API_KEY", ""))  # Will be set from environment


class SkillRubric(BaseModel):
    hard_skills: list[str] = Field(default_factory=list, description="Technical skills: Kotlin, Python, etc.")
    soft_skills: list[str] = Field(default_factory=list, description="Soft skills: Leadership, Communication, etc.")
    must_have_phrases: list[str] = Field(default_factory=list, description="Exact phrases that signal match")
    tools_and_frameworks: list[str] = Field(default_factory=list, description="Libraries, tools, platforms")
    experience_requirements: str = Field(default="", description="Years of experience or level required")
    salary_range: str = Field(default="", description="Salary or compensation info")
    company_culture_signals: list[str] = Field(default_factory=list, description="Culture fit indicators")


class JobAuditorService:
    """Analyzes job descriptions to extract keywords and rubric"""

    AUDIT_PROMPT = """You are a resume optimization expert. Analyze this job description and extract a structured keyword rubric.

Job Description:
{jd_text}

Return a JSON object with:
{{
  "hard_skills": ["skill1", "skill2", ...],
  "soft_skills": ["communication", "leadership", ...],
  "must_have_phrases": ["exact phrases that appear", ...],
  "tools_and_frameworks": ["tool1", "framework1", ...],
  "experience_requirements": "X+ years or level",
  "salary_range": "salary info if mentioned",
  "company_culture_signals": ["culture indicators", ...]
}}

Be specific. Extract actual keywords from the JD. Focus on what makes a candidate stand out."""

    async def audit_job_description(self, jd_text: str) -> SkillRubric:
        """
        Extract structured keyword rubric from job description
        
        Args:
            jd_text: Raw job description text
            
        Returns:
            SkillRubric with extracted keywords and requirements
        """
        try:
            logger.info("[AUDITOR] Starting JD analysis...")
            
            # Call Gemini to extract structured data
            model = genai.GenerativeModel("gemini-pro")
            prompt = self.AUDIT_PROMPT.format(jd_text=jd_text)
            
            response = await self._call_gemini_async(model, prompt)
            
            # Parse JSON response
            try:
                # Extract JSON from response (might be wrapped in markdown)
                json_str = response.strip()
                if json_str.startswith("```"):
                    json_str = json_str.split("```")[1].lstrip("json\n")
                if json_str.endswith("```"):
                    json_str = json_str[:-3]
                
                data = json.loads(json_str)
                rubric = SkillRubric(**data)
                
                logger.info(f"[AUDITOR] Extracted {len(rubric.hard_skills)} hard skills, {len(rubric.soft_skills)} soft skills")
                return rubric
                
            except json.JSONDecodeError as e:
                logger.error(f"[AUDITOR] Failed to parse JSON: {e}")
                logger.error(f"[AUDITOR] Response was: {response[:200]}")
                return SkillRubric()  # Return empty rubric on parse error
                
        except Exception as e:
            logger.error(f"[AUDITOR] Audit failed: {e}")
            raise

    async def _call_gemini_async(self, model, prompt: str) -> str:
        """Wrapper for synchronous Gemini API call"""
        try:
            response = model.generate_content(prompt)
            return response.text
        except Exception as e:
            logger.error(f"[AUDITOR] Gemini API error: {e}")
            raise


# Singleton instance
_auditor = None


def get_auditor():
    """Get or create auditor instance"""
    global _auditor
    if _auditor is None:
        _auditor = JobAuditorService()
    return _auditor

"""
Grader Service - Validates and scores tailored resumes

The Grader acts as a recruiter to validate:
- Keyword density matches JD requirements
- Professional tone and grammar
- STAR method application
- Relevance and alignment

Returns a score and rejection reason if quality is too low for retry.
"""

import logging
import os
from typing import Optional
import google.generativeai as genai
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Configure Gemini
genai.configure(api_key=os.getenv("GEMINI_API_KEY", ""))


class GradeResult(BaseModel):
    score: float = Field(default=0.0, ge=0.0, le=100.0, description="Quality score 0-100")
    passed: bool = Field(default=False, description="True if resume passes quality threshold (75+)")
    keyword_coverage: float = Field(default=0.0, description="% of JD keywords found in resume")
    tone_feedback: str = Field(default="", description="Feedback on tone and professionalism")
    alignment_issues: list[str] = Field(default_factory=list, description="Areas that need improvement")
    retry_prompt: Optional[str] = Field(default=None, description="Specific instruction for retry if failed")


class ResumeGraderService:
    """Grades and validates tailored resumes before returning to user"""

    GRADE_PROMPT = """You are a senior recruiter screening resumes. Rate this tailored resume against the job description.

Resume:
{resume_text}

Job Description:
{jd_text}

Evaluate:
1. Keyword coverage: % of JD keywords present (hard skills, tools, tools)
2. Tone: Professional, quantified, action-oriented
3. STAR method: Situation-Task-Action-Result format for achievements
4. Relevance: How well does it target this specific role

Return a JSON response:
{{
  "score": <0-100>,
  "passed": <true if score >= 75>,
  "keyword_coverage": <0-100>,
  "tone_feedback": "feedback on tone, professionalism, clarity",
  "alignment_issues": ["issue1", "issue2", ...],
  "retry_prompt": "If score < 75, provide specific instruction to improve. Otherwise null."
}}

Be objective. High standards for quality."""

    async def grade_resume(self, resume_text: str, jd_text: str) -> GradeResult:
        """
        Grade a tailored resume against JD requirements
        
        Args:
            resume_text: The tailored resume to grade
            jd_text: Original job description for reference
            
        Returns:
            GradeResult with score, feedback, and retry instruction if needed
        """
        try:
            logger.info("[GRADER] Starting resume evaluation...")
            
            model = genai.GenerativeModel("gemini-pro")
            prompt = self.GRADE_PROMPT.format(resume_text=resume_text, jd_text=jd_text)
            
            response = await self._call_gemini_async(model, prompt)
            
            # Parse JSON response
            import json
            try:
                json_str = response.strip()
                if json_str.startswith("```"):
                    json_str = json_str.split("```")[1].lstrip("json\n")
                if json_str.endswith("```"):
                    json_str = json_str[:-3]
                
                data = json.loads(json_str)
                result = GradeResult(**data)
                
                logger.info(f"[GRADER] Resume scored {result.score}/100 - {'PASSED' if result.passed else 'FAILED'}")
                logger.info(f"[GRADER] Keyword coverage: {result.keyword_coverage}%")
                
                return result
                
            except json.JSONDecodeError as e:
                logger.error(f"[GRADER] Failed to parse JSON: {e}")
                return GradeResult(score=50.0, passed=False)
                
        except Exception as e:
            logger.error(f"[GRADER] Grade failed: {e}")
            raise

    async def _call_gemini_async(self, model, prompt: str) -> str:
        """Wrapper for synchronous Gemini API call"""
        try:
            response = model.generate_content(prompt)
            return response.text
        except Exception as e:
            logger.error(f"[GRADER] Gemini API error: {e}")
            raise


# Singleton instance
_grader = None


def get_grader():
    """Get or create grader instance"""
    global _grader
    if _grader is None:
        _grader = ResumeGraderService()
    return _grader

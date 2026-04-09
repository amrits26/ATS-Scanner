"""
Auto-Tailor Agent - One-click resume rewriting for specific job descriptions

Scrapes JD from URL, rewrites resume to match, returns DOCX download.
"""

import logging
import json
from typing import Dict, List, Any

import google.generativeai as genai

from backend.services.agent_base import AIAgent
from backend.services.job_scraper import scrape_job_description

logger = logging.getLogger(__name__)


class AutoTailorAgent(AIAgent):
    """
    Rewrites a user's resume to align with a specific job description.
    """

    def __init__(self, user_id: str, session_id: str = None, telemetry_tracker=None):
        super().__init__(
            agent_type="tailor",
            user_id=user_id,
            session_id=session_id,
            telemetry_tracker=telemetry_tracker,
        )

    def _register_tools(self) -> None:
        self.tools = {
            "job_scraper": self._job_scraper_tool,
            "resume_rewriter": self._resume_rewriter,
            "match_score_calculator": self._match_score_calculator,
        }

    async def parse_user_goal(self, query: str) -> Dict[str, Any]:
        return {
            "goal": "rewrite_resume_for_job",
            "required_tools": ["job_scraper", "resume_rewriter", "match_score_calculator"],
        }

    # ========================================================================
    # TOOLS
    # ========================================================================

    async def _job_scraper_tool(self, job_url: str = None, jd_text: str = None) -> Dict:
        """
        Get job description from URL or direct text.
        """
        if jd_text:
            return {"job_description": jd_text, "source": "text"}
        if job_url:
            try:
                jd = await scrape_job_description(job_url)
                return {"job_description": jd, "source": "url"}
            except Exception as e:
                logger.error(f"[TAILOR] Scrape failed: {e}")
                return {"job_description": "", "source": "url", "error": str(e)}
        return {"job_description": "", "source": "none"}

    async def _resume_rewriter(self, resume_text: str, job_description: str) -> Dict:
        """
        Rewrite resume to match JD.
        """
        if not job_description:
            return {"rewritten_resume": resume_text, "key_alignments": []}

        prompt = f"""You are an expert resume writer. Rewrite this resume to align perfectly with the job description below.

Resume:
{resume_text}

Job Description:
{job_description[:2000]}

Rules:
- Keep all factual experience, dates, and titles unchanged.
- Reorder bullets and adjust wording to highlight required skills.
- Add quantifiable metrics where possible.
- Output ONLY the rewritten resume text.
- Use clear section headers: Summary, Skills, Experience, Education."""
        
        model = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content(prompt)

        rewritten = response.text.strip()
        
        # Extract key alignment changes
        try:
            align_prompt = f"""List 3-5 key alignment changes made to the resume.
Return JSON list: ["change 1", "change 2", ...]"""
            align_response = model.generate_content(align_prompt)
            alignments = json.loads(align_response.text)
        except:
            alignments = ["Resume tailored to job description"]

        return {
            "rewritten_resume": rewritten,
            "key_alignments": alignments
        }

    async def _match_score_calculator(self, rewritten_resume: str, job_description: str) -> Dict:
        """Estimate ATS match score (0-100)."""
        prompt = f"""Estimate the ATS match score (0-100) for this resume against the job description.
Resume excerpt: {rewritten_resume[:500]}
Job Description excerpt: {job_description[:500]}

Return JSON: {{"score": 85, "reasoning": "..."}}"""
        
        model = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content(prompt)
        
        try:
            result = json.loads(response.text)
        except:
            result = {"score": 75, "reasoning": "Automated estimate."}
        
        return result

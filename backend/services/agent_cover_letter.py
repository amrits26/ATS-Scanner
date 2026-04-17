"""
Cover Letter Agent – Generates hyper-personalized cover letters.

Think → Act → Reflect pattern (extends AIAgent).

Tools:
  company_researcher  – scrape company about-page for culture/mission signals
  letter_drafter      – Gemini-powered letter using resume + JD + company intel
  tone_adjuster       – match requested tone (formal | conversational | storytelling)
"""

import json
import logging
from typing import Any, Dict, Optional

from backend.services.agent_base import AIAgent

logger = logging.getLogger(__name__)


class CoverLetterAgent(AIAgent):
    """Generates personalized cover letters using resume, JD, and company research."""

    def __init__(self, user_id: str, session_id: str = None, telemetry_tracker=None):
        super().__init__(
            agent_type="cover_letter",
            user_id=user_id,
            session_id=session_id,
            telemetry_tracker=telemetry_tracker,
        )

    def _register_tools(self) -> None:
        self.tools = {
            "company_researcher": self._company_researcher,
            "letter_drafter": self._letter_drafter,
            "tone_adjuster": self._tone_adjuster,
        }

    async def parse_user_goal(self, query: str) -> Dict[str, Any]:
        return {
            "goal": "generate_cover_letter",
            "required_tools": ["company_researcher", "letter_drafter"],
        }

    # ========================================================================
    # TOOLS
    # ========================================================================

    async def _company_researcher(self, company_name: str, company_url: Optional[str] = None) -> Dict[str, str]:
        """
        Extract company mission, culture, and values from their website.
        Uses trafilatura for clean text extraction if a URL is provided.
        """
        about_text = ""
        if company_url:
            try:
                import trafilatura  # already in requirements
                downloaded = trafilatura.fetch_url(company_url)
                if downloaded:
                    about_text = trafilatura.extract(downloaded) or ""
                    about_text = about_text[:2000]  # cap to avoid token bloat
            except Exception as e:
                logger.warning(f"[CoverLetter] Company research fetch failed: {e}")

        if not about_text:
            # Fallback: ask Gemini to recall what it knows about the company
            prompt = f"""Provide a brief (3-4 sentence) summary of {company_name}'s company culture, mission, and values.
Return ONLY the summary text, no headers or markdown."""
            text, usage = await self.call_gemini(prompt, temperature=self.TEMPERATURE_SCORING)
            about_text = text

        return {"company_name": company_name, "about": about_text}

    async def _letter_drafter(
        self,
        resume_text: str,
        job_description: str,
        company_intel: Dict[str, str],
        tone: str = "professional",
        word_count: int = 350,
    ) -> Dict[str, str]:
        """
        Draft the cover letter using Gemini.
        Returns {letter, subject_line, key_hooks}.
        """
        company_name = company_intel.get("company_name", "the company")
        about = company_intel.get("about", "")

        prompt = f"""You are an expert cover letter writer. Write a compelling {tone} cover letter.

Resume:
{resume_text[:2500]}

Job Description:
{job_description[:1500]}

Company Background:
{about}

Requirements:
- Tone: {tone} (formal | conversational | storytelling)
- Target word count: ~{word_count} words
- Open with a hook that references the company's mission or a specific JD detail
- Highlight 2-3 specific achievements from the resume that map to JD requirements
- Close with a confident call-to-action
- Do NOT use generic phrases like "I am writing to apply..."

Return ONLY valid JSON:
{{
    "letter": "Full cover letter text...",
    "subject_line": "Suggested email subject line",
    "key_hooks": ["hook 1", "hook 2", "hook 3"]
}}"""

        text, usage = await self.call_gemini(prompt, temperature=self.TEMPERATURE_CREATIVE, json_mode=True)

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {
                "letter": text,
                "subject_line": f"Application – {company_name}",
                "key_hooks": [],
            }

    async def _tone_adjuster(self, letter: str, target_tone: str) -> Dict[str, str]:
        """
        Rewrite a drafted letter to match a specific tone.
        target_tone: formal | conversational | storytelling
        """
        prompt = f"""Rewrite the following cover letter in a {target_tone} tone.
Keep all factual content and achievements. Only adjust voice and style.
Return ONLY the rewritten letter text, no additional commentary.

Original letter:
{letter}"""

        text, usage = await self.call_gemini(prompt, temperature=self.TEMPERATURE_CREATIVE)
        return {"letter": text, "tone": target_tone}

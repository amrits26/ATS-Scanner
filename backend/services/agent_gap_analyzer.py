"""
Gap Analyzer Agent – Identifies skill/experience gaps between a resume and a job description,
then generates targeted interview-style questions to fill those gaps.

Think → Act → Reflect pattern (extends AIAgent).

Tools:
  gap_detector      – diff resume vs JD, list missing signals
  question_generator – create targeted fill-gap questions for the user
  context_builder   – build enriched context dict for the tailor pipeline
"""

import json
import logging
from typing import Any, Dict, List

from backend.services.agent_base import AIAgent

logger = logging.getLogger(__name__)


class GapAnalyzerAgent(AIAgent):
    """
    Surfaces skill/experience gaps and generates targeted questions for the user.
    Output feeds directly into AutoTailorAgent (via AgentOrchestrator).
    """

    def __init__(self, user_id: str, session_id: str = None, telemetry_tracker=None):
        super().__init__(
            agent_type="gap_analyzer",
            user_id=user_id,
            session_id=session_id,
            telemetry_tracker=telemetry_tracker,
        )

    def _register_tools(self) -> None:
        self.tools = {
            "gap_detector": self._gap_detector,
            "question_generator": self._question_generator,
            "context_builder": self._context_builder,
        }

    async def parse_user_goal(self, query: str) -> Dict[str, Any]:
        return {
            "goal": "analyze_gaps_and_generate_questions",
            "required_tools": ["gap_detector", "question_generator", "context_builder"],
        }

    # ========================================================================
    # TOOLS
    # ========================================================================

    async def _gap_detector(
        self, resume_text: str, job_description: str
    ) -> Dict[str, Any]:
        """
        Use Gemini to identify missing skills, tools, and experience gaps.
        Returns structured list of gaps with severity and category.
        """
        prompt = f"""You are an expert ATS analyst. Compare this resume against the job description.

Resume:
{resume_text[:3000]}

Job Description:
{job_description[:2000]}

Identify all gaps: skills the JD requires that the resume does NOT demonstrate.
Return ONLY valid JSON, no markdown:
{{
    "hard_skill_gaps": [
        {{"term": "Kubernetes", "category": "DevOps", "severity": "critical"}}
    ],
    "soft_skill_gaps": [
        {{"term": "cross-functional leadership", "category": "leadership", "severity": "moderate"}}
    ],
    "experience_gaps": [
        {{"term": "5+ years Python", "category": "experience", "severity": "critical"}}
    ],
    "missing_keywords": ["CI/CD", "Terraform", "REST APIs"]
}}"""

        text, usage = await self.call_gemini(prompt, temperature=self.TEMPERATURE_SCORING, json_mode=True)

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logger.warning("[GapAnalyzer] JSON parse failed, returning raw text")
            return {"raw": text, "hard_skill_gaps": [], "soft_skill_gaps": [], "experience_gaps": [], "missing_keywords": []}

    async def _question_generator(
        self, gaps: Dict[str, Any], job_description: str
    ) -> List[Dict[str, str]]:
        """
        Generate 3-6 targeted questions that help us extract missing context from the user
        so that AutoTailorAgent can write stronger bullets.
        """
        all_gaps: List[str] = []
        for key in ("hard_skill_gaps", "soft_skill_gaps", "experience_gaps"):
            for g in gaps.get(key, []):
                if isinstance(g, dict):
                    all_gaps.append(g.get("term", ""))
        all_gaps += gaps.get("missing_keywords", [])
        all_gaps = [g for g in all_gaps if g][:8]

        if not all_gaps:
            return []

        prompt = f"""You are a senior career coach. Given these resume gaps, generate 3-6 concise questions
that will extract the user's real experience in these areas so their resume can be strengthened.

Identified gaps: {", ".join(all_gaps)}

Job Description excerpt:
{job_description[:800]}

Rules:
- Questions should be specific and easy to answer in 1-3 sentences
- Focus on concrete experiences, not theoretical knowledge
- Return ONLY valid JSON:
[
  {{"id": "q1", "gap": "Kubernetes", "question": "Describe a time you deployed or managed a Kubernetes cluster in production. What was the scale?"}},
  ...
]"""

        text, usage = await self.call_gemini(prompt, temperature=self.TEMPERATURE_SCORING, json_mode=True)

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logger.warning("[GapAnalyzer] Question JSON parse failed")
            return []

    async def _context_builder(
        self,
        resume_text: str,
        job_description: str,
        gaps: Dict[str, Any],
        questions: List[Dict],
        user_answers: Dict[str, str] = None,
    ) -> Dict[str, Any]:
        """
        Merge gap analysis output with user answers into a rich context dict
        ready for AutoTailorAgent.
        """
        extra_context = ""
        if user_answers:
            lines = []
            for q in questions:
                qid = q.get("id", "")
                answer = user_answers.get(qid, "")
                if answer:
                    lines.append(f"Q: {q.get('question', '')}\nA: {answer}")
            extra_context = "\n\n".join(lines)

        return {
            "resume_text": resume_text,
            "job_description": job_description,
            "gaps": gaps,
            "questions": questions,
            "user_answers": user_answers or {},
            "extra_context_for_tailor": extra_context,
        }

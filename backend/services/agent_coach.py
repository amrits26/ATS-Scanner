"""
Resume Coach Agent - Interactive resume improvement guidance

User: "How do I improve my data science resume?"
Agent analyzes bullets, identifies weak points, generates rewrites with metrics.
"""

import logging
import json
from typing import Dict, List, Any

import google.generativeai as genai

from backend.services.agent_base import AIAgent

logger = logging.getLogger(__name__)


class ResumeCoachAgent(AIAgent):
    """
    Helps users improve their resume through personalized analysis and recommendations.
    
    Tools:
    1. strength_analyzer - Identify strong bullets and patterns
    2. gap_detector - Find weak bullets vs. industry standards
    3. bullet_rewriter - Generate 5 rewrite options with metrics
    4. industry_benchmark - Compare against top performers in role
    5. action_plan_generator - Create 30-day improvement plan
    """

    def __init__(self, user_id: str, session_id: str = None, telemetry_tracker=None):
        super().__init__(
            agent_type="coach",
            user_id=user_id,
            session_id=session_id,
            telemetry_tracker=telemetry_tracker,
        )

    def _register_tools(self) -> None:
        """Register all tools for coach agent"""
        self.tools = {
            "strength_analyzer": self._strength_analyzer,
            "gap_detector": self._gap_detector,
            "bullet_rewriter": self._bullet_rewriter,
            "industry_benchmark": self._industry_benchmark,
            "action_plan_generator": self._action_plan_generator,
        }

    async def parse_user_goal(self, query: str) -> Dict[str, Any]:
        """
        Parse user query into structured goal.
        """
        return {
            "goal": "improve_resume_bullets",
            "context": {"user_question": query},
            "required_tools": ["strength_analyzer", "gap_detector"],
        }

    # ========================================================================
    # TOOLS
    # ========================================================================

    async def _strength_analyzer(self, resume_text: str) -> Dict[str, Any]:
        """
        Analyze resume for strong bullets and patterns.
        """
        prompt = f"""Analyze this resume for STRONG bullets and patterns:

{resume_text[:2000]}

Find:
1. Strongest 3 bullets (ones with metrics, action verbs, business impact)
2. Recurring patterns (what makes good bullets?)
3. Score each category 1-5: metric usage, action verbs, business impact

Return JSON: {{"strong_bullets": [...], "patterns": [...], "score_breakdown": {{...}}}}"""

        try:
            model = genai.GenerativeModel("gemini-1.5-flash")
            response = model.generate_content(prompt)
            result = json.loads(response.text)
            logger.info(f"[COACH] Strength analysis complete")
            return result
        except Exception as e:
            logger.error(f"[COACH] Strength analyzer failed: {e}")
            return {
                "strong_bullets": [],
                "patterns": ["Could not analyze"],
                "score_breakdown": {},
            }

    async def _gap_detector(
        self, resume_text: str, job_description: str = None
    ) -> Dict[str, Any]:
        """
        Identify weak bullets and gaps vs. industry standards.
        """
        prompt = f"""Find WEAK bullets and gaps in this resume:

{resume_text[:2000]}

Compare to industry standard for technical roles.

Return JSON:
{{
  "weak_bullets": [
    {{"text": "original bullet", "issue": "reason it's weak", "severity": "high|medium|low"}},
    ...
  ],
  "credential_gaps": ["missing cert or skill"],
  "style_gaps": ["formatting issue"]
}}"""

        try:
            model = genai.GenerativeModel("gemini-1.5-flash")
            response = model.generate_content(prompt)
            result = json.loads(response.text)
            logger.info(f"[COACH] Gap detection complete")
            return result
        except Exception as e:
            logger.error(f"[COACH] Gap detector failed: {e}")
            return {
                "weak_bullets": [],
                "credential_gaps": [],
                "style_gaps": [],
            }

    async def _bullet_rewriter(
        self, weak_bullet: str, industry: str = "tech"
    ) -> Dict[str, List[str]]:
        """
        Generate 5 rewrite options for a weak bullet.
        """
        prompt = f"""Rewrite this bullet point 5 different ways, each with metrics and impact:

Original: "{weak_bullet}"

Generate 5 strong rewrites for {industry} industry.
Each should:
- Include 1-2 metrics/numbers
- Use power verbs
- Show business impact
- Be 15-20 words max

Return JSON: {{"rewrites": [...], "tips": [...]}}"""

        try:
            model = genai.GenerativeModel("gemini-1.5-flash")
            response = model.generate_content(prompt)
            result = json.loads(response.text)
            logger.info(f"[COACH] Bullet rewriter complete")
            return result
        except Exception as e:
            logger.error(f"[COACH] Bullet rewriter failed: {e}")
            return {
                "rewrites": [f"Improved version of: {weak_bullet}"],
                "tips": [],
            }

    async def _industry_benchmark(self, target_role: str) -> Dict[str, Any]:
        """
        Get industry benchmarks for a role.
        """
        prompt = f"""Get industry benchmarks for: {target_role}

What do top candidates have in their resume?

Return JSON:
{{
  "avg_salary": 150000,
  "must_have_skills": ["skill1", "skill2"],
  "nice_to_haves": ["optional"],
  "experience_years": 5,
  "typical_background": "CS degree or bootcamp"
}}"""

        try:
            model = genai.GenerativeModel("gemini-1.5-flash")
            response = model.generate_content(prompt)
            result = json.loads(response.text)
            logger.info(f"[COACH] Benchmark complete for {target_role}")
            return result
        except Exception as e:
            logger.error(f"[COACH] Benchmark failed: {e}")
            return {
                "avg_salary": 0,
                "must_have_skills": [],
                "nice_to_haves": [],
                "experience_years": 0,
            }

    async def _action_plan_generator(
        self, weak_areas: List[str], target_role: str
    ) -> Dict[str, Any]:
        """
        Create a 30-day improvement plan.
        """
        prompt = f"""Create a 30-day resume improvement plan.

Weak areas: {weak_areas}
Target role: {target_role}

Break into:
- Week 1-4 actionable tasks (specific, measurable)
- Quick wins (do in 2-3 hours)
- Long term (2-3 months)

Return JSON with week_1, week_2, week_3, week_4, quick_wins, long_term lists."""

        try:
            model = genai.GenerativeModel("gemini-1.5-flash")
            response = model.generate_content(prompt)
            result = json.loads(response.text)
            logger.info(f"[COACH] Action plan generated")
            return result
        except Exception as e:
            logger.error(f"[COACH] Action plan generator failed: {e}")
            return {
                "week_1": [],
                "week_2": [],
                "quick_wins": [],
                "long_term": [],
            }

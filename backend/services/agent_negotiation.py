"""
Negotiation Advisor Agent – Salary negotiation strategy and scripts.

Think → Act → Reflect pattern (extends AIAgent).

Tools:
  market_benchmarker  – estimate market-rate compensation range for the role
  strategy_builder    – create step-by-step negotiation game plan
  script_generator    – write ready-to-send counter-offer email + talking points
"""

import json
import logging
from typing import Any, Dict, Optional

from backend.services.agent_base import AIAgent

logger = logging.getLogger(__name__)


class NegotiationAdvisorAgent(AIAgent):
    """Coaches users through salary negotiation with market data and tailored scripts."""

    def __init__(self, user_id: str, session_id: str = None, telemetry_tracker=None):
        super().__init__(
            agent_type="negotiation",
            user_id=user_id,
            session_id=session_id,
            telemetry_tracker=telemetry_tracker,
        )

    def _register_tools(self) -> None:
        self.tools = {
            "market_benchmarker": self._market_benchmarker,
            "strategy_builder": self._strategy_builder,
            "script_generator": self._script_generator,
        }

    async def parse_user_goal(self, query: str) -> Dict[str, Any]:
        return {
            "goal": "negotiate_salary",
            "required_tools": ["market_benchmarker", "strategy_builder", "script_generator"],
        }

    # ========================================================================
    # TOOLS
    # ========================================================================

    async def _market_benchmarker(
        self,
        job_title: str,
        company: str,
        location: str,
        years_experience: int = 0,
        current_offer: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Use Gemini to estimate a realistic compensation range with supporting rationale.
        Returns p25/p50/p75 salary estimates and total comp guidance.
        """
        prompt = f"""You are a compensation analyst. Estimate realistic total compensation for:

Role: {job_title}
Company: {company}
Location: {location}
Years of experience: {years_experience}
Current offer (if provided): {f"${current_offer:,.0f}" if current_offer else "Not provided"}

Provide a realistic salary range based on current market data (use your training knowledge):
Return ONLY valid JSON:
{{
    "p25_base": 95000,
    "p50_base": 115000,
    "p75_base": 135000,
    "total_comp_note": "Senior SWE at mid-size SF company includes RSUs…",
    "negotiation_headroom": "10-15% above offer typical for this role",
    "key_data_points": [
        "Glassdoor median for {job_title} in {location}: $X",
        "levels.fyi shows similar FAANG-adjacent roles at $X-$Y"
    ]
}}"""

        text, usage = await self.call_gemini(prompt, temperature=self.TEMPERATURE_SCORING, json_mode=True)

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {
                "p25_base": None,
                "p50_base": None,
                "p75_base": None,
                "total_comp_note": text,
                "negotiation_headroom": "Typically 10-15% above initial offer",
                "key_data_points": [],
            }

    async def _strategy_builder(
        self,
        market_data: Dict[str, Any],
        current_offer: Optional[float],
        target_salary: Optional[float],
        job_title: str,
        years_experience: int = 0,
    ) -> Dict[str, Any]:
        """
        Build a step-by-step negotiation strategy tailored to the user's situation.
        """
        p50 = market_data.get("p50_base", "N/A")
        headroom = market_data.get("negotiation_headroom", "10-15%")

        context = f"""
Role: {job_title}
YOE: {years_experience}
Market P50: ${p50:,.0f if isinstance(p50, (int, float)) else p50}
Current offer: {f"${current_offer:,.0f}" if current_offer else "Not yet received"}
Target salary: {f"${target_salary:,.0f}" if target_salary else "Not specified"}
Typical headroom: {headroom}
"""

        prompt = f"""You are a top career negotiation coach. Build a concrete negotiation strategy.
{context}

Return ONLY valid JSON:
{{
    "opening_ask": 125000,
    "walk_away_number": 105000,
    "batna": "Current role pays $X + competing offer from Y",
    "phases": [
        {{
            "phase": 1,
            "action": "Express enthusiasm, ask for time to review",
            "timing": "Same day as offer"
        }},
        {{
            "phase": 2,
            "action": "Counter with market-anchored ask",
            "timing": "24-48 hours later"
        }},
        {{
            "phase": 3,
            "action": "Negotiate non-salary if base is firm",
            "timing": "After counter response"
        }}
    ],
    "non_salary_levers": ["signing bonus", "extra PTO", "remote flexibility", "RSU acceleration"],
    "risk_level": "low"
}}"""

        text, usage = await self.call_gemini(prompt, temperature=self.TEMPERATURE_SCORING, json_mode=True)

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"raw_strategy": text, "phases": [], "non_salary_levers": []}

    async def _script_generator(
        self,
        strategy: Dict[str, Any],
        job_title: str,
        company: str,
        hiring_manager_name: Optional[str] = None,
    ) -> Dict[str, str]:
        """
        Write a ready-to-send counter-offer email and verbal talking points.
        """
        opening_ask = strategy.get("opening_ask", "")
        levers = ", ".join(strategy.get("non_salary_levers", [])[:3])
        recipient = hiring_manager_name or "the hiring manager"

        prompt = f"""Write a polished counter-offer email and 3 key talking points for a phone/video negotiation.

Role: {job_title} at {company}
Recipient: {recipient}
Target ask: ${opening_ask:,.0f if isinstance(opening_ask, (int, float)) else opening_ask}
Non-salary levers if base is firm: {levers}

Return ONLY valid JSON:
{{
    "email_subject": "Re: {job_title} Offer – Following Up",
    "email_body": "Full email text...",
    "talking_points": [
        "Point 1: Lead with enthusiasm and market data...",
        "Point 2: Anchor to your value, not personal need...",
        "Point 3: Offer flexibility on non-salary items..."
    ],
    "one_liner_counter": "Quick verbal counter phrase to use on the spot"
}}"""

        text, usage = await self.call_gemini(prompt, temperature=self.TEMPERATURE_CREATIVE, json_mode=True)

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {
                "email_subject": f"Re: {job_title} Offer",
                "email_body": text,
                "talking_points": [],
                "one_liner_counter": "",
            }

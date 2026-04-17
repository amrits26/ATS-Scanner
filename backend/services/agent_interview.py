"""
Interview Prep Agent - Generate role-specific questions and STAR answers
"""

import logging
import json
from typing import Dict, List, Any

from backend.services.agent_base import AIAgent

logger = logging.getLogger(__name__)


class InterviewPrepAgent(AIAgent):
    """
    Prepares user for job interviews with customized questions and responses.
    """

    def __init__(self, user_id: str, session_id: str = None, telemetry_tracker=None):
        super().__init__(
            agent_type="interview",
            user_id=user_id,
            session_id=session_id,
            telemetry_tracker=telemetry_tracker,
        )

    def _register_tools(self) -> None:
        self.tools = {
            "question_generator": self._question_generator,
            "star_answer_generator": self._star_answer_generator,
        }

    async def parse_user_goal(self, query: str) -> Dict[str, Any]:
        return {
            "goal": "prepare_interview",
            "required_tools": ["question_generator", "star_answer_generator"],
        }

    # ========================================================================
    # TOOLS
    # ========================================================================

    async def _question_generator(
        self, job_title: str, company: str, resume_text: str = ""
    ) -> Dict:
        """
        Generate likely interview questions categorized by type.
        """
        prompt = f"""Generate 15 likely interview questions for a {job_title} position at {company}.

Include:
- 5 technical questions related to required skills
- 5 behavioral questions (STAR method)
- 3 culture-fit questions
- 2 questions about the candidate's resume

Return JSON:
{{
  "technical": [list of questions],
  "behavioral": [list of questions],
  "culture_fit": [list],
  "resume_specific": [list]
}}"""
        
        text, usage = await self.call_gemini(prompt, temperature=self.TEMPERATURE_SCORING, json_mode=True)
        
        try:
            return json.loads(text)
        except:
            return {"technical": [], "behavioral": [], "culture_fit": [], "resume_specific": []}

    async def _star_answer_generator(self, questions: List[str], resume_text: str) -> Dict:
        """
        For each behavioral question, create a STAR-method answer skeleton.
        """
        if not questions:
            return {"star_answers": []}
        
        q_list = "\n".join(questions[:5])
        prompt = f"""For each of these behavioral questions, provide a STAR-method answer skeleton.

Questions:
{q_list}

Return JSON array:
[
  {{
    "question": "Tell me about a time...",
    "star_template": {{
      "situation": "...",
      "task": "...",
      "action": "...",
      "result": "..."
    }},
    "sample_answer": "Full example answer..."
  }}
]"""
        
        text, usage = await self.call_gemini(prompt, temperature=self.TEMPERATURE_CREATIVE, json_mode=True)
        
        try:
            return {"star_answers": json.loads(text)}
        except:
            return {"star_answers": []}

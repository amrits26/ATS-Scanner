"""
Agent Training Pipeline – Reinforcement Learning Loop

Collects user feedback (accepts, edits, rejections) on agent outputs,
generates synthetic training examples, and provides few-shot injection
for in-context learning.

Flow:
  1. Agent produces output → user reacts (accept/edit/reject)
  2. log_agent_interaction() stores the signal in agent_feedback_log
  3. When enough high-quality signals exist, generate_synthetic_examples()
     creates new training data via Gemini
  4. get_few_shot_examples() retrieves top examples for prompt augmentation
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db_models import AgentFeedbackLog, AgentOutcomeFeedback, Job

logger = logging.getLogger(__name__)

# Minimum high-quality examples before triggering synthetic generation
MIN_EXAMPLES_FOR_SYNTHESIS = 5


class AgentTrainingPipeline:
    """Manages collection, synthesis, and retrieval of agent training examples."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # 1. LOG INTERACTIONS
    # ------------------------------------------------------------------

    async def log_agent_interaction(
        self,
        agent_type: str,
        user_id: str,
        job_id: Optional[str],
        input_context: Dict[str, Any],
        agent_output: Dict[str, Any],
        user_action: str,
        user_edited_output: Optional[Dict[str, Any]] = None,
        rating: Optional[int] = None,
    ) -> AgentFeedbackLog:
        """Log every agent output + user reaction for training."""

        edit_distance = None
        if user_edited_output and agent_output:
            edit_distance = _levenshtein_ratio(
                json.dumps(agent_output, sort_keys=True),
                json.dumps(user_edited_output, sort_keys=True),
            )

        # Infer rating from action if not provided
        if rating is None:
            if user_action in ("accepted", "applied"):
                rating = 5
            elif user_action == "edited":
                rating = max(1, int(5 * (edit_distance or 0.7)))
            else:
                rating = 1

        entry = AgentFeedbackLog(
            agent_type=agent_type,
            user_id=user_id,
            job_id=job_id,
            input_context=input_context,
            agent_output=agent_output,
            user_action=user_action,
            user_edited_output=user_edited_output,
            edit_distance=edit_distance,
            rating=rating,
            is_synthetic=False,
        )
        self.db.add(entry)
        await self.db.commit()
        await self.db.refresh(entry)

        # Auto-generate synthetic if enough high-quality data
        await self._maybe_generate_synthetic(agent_type, job_id)

        return entry

    # ------------------------------------------------------------------
    # 2. FEW-SHOT RETRIEVAL
    # ------------------------------------------------------------------

    async def get_few_shot_examples(
        self,
        agent_type: str,
        input_context: Optional[Dict[str, Any]] = None,
        limit: int = 3,
        min_rating: int = 4,
    ) -> List[AgentFeedbackLog]:
        """Retrieve high-rated examples for few-shot prompt injection."""

        # Try job-specific match first
        job_id = (input_context or {}).get("job_id")
        if job_id:
            stmt = (
                select(AgentFeedbackLog)
                .where(
                    and_(
                        AgentFeedbackLog.agent_type == agent_type,
                        AgentFeedbackLog.job_id == job_id,
                        AgentFeedbackLog.rating >= min_rating,
                    )
                )
                .order_by(
                    AgentFeedbackLog.rating.desc(),
                    AgentFeedbackLog.created_at.desc(),
                )
                .limit(limit)
            )
            result = await self.db.execute(stmt)
            examples = list(result.scalars().all())
            if examples:
                await self._bump_usage(examples)
                return examples

        # Fallback: recent high-rated examples for this agent type
        stmt = (
            select(AgentFeedbackLog)
            .where(
                and_(
                    AgentFeedbackLog.agent_type == agent_type,
                    AgentFeedbackLog.rating >= min_rating,
                )
            )
            .order_by(
                AgentFeedbackLog.rating.desc(),
                AgentFeedbackLog.created_at.desc(),
            )
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        examples = list(result.scalars().all())
        await self._bump_usage(examples)
        return examples

    async def build_few_shot_prompt(
        self,
        agent_type: str,
        input_context: Dict[str, Any],
        base_prompt: str,
        max_examples: int = 2,
    ) -> str:
        """Augment a base prompt with relevant few-shot examples."""

        examples = await self.get_few_shot_examples(
            agent_type, input_context, limit=max_examples
        )
        if not examples:
            return base_prompt

        few_shot_text = "\n\nHere are examples of high-quality outputs for similar scenarios:\n"
        for i, ex in enumerate(examples, 1):
            input_snippet = json.dumps(ex.input_context, indent=2)[:500]
            output_snippet = json.dumps(ex.agent_output, indent=2)[:500]
            few_shot_text += (
                f"\nExample {i}:\n"
                f"Input Context: {input_snippet}...\n"
                f"Output: {output_snippet}...\n"
            )

        return (
            base_prompt
            + few_shot_text
            + "\n\nNow, produce a similarly high-quality output for the current input."
        )

    # ------------------------------------------------------------------
    # 3. SYNTHETIC EXAMPLE GENERATION
    # ------------------------------------------------------------------

    async def _maybe_generate_synthetic(
        self, agent_type: str, job_id: Optional[str]
    ):
        """Trigger synthetic generation when enough real high-quality data exists."""

        count_stmt = select(func.count(AgentFeedbackLog.id)).where(
            and_(
                AgentFeedbackLog.agent_type == agent_type,
                AgentFeedbackLog.rating >= 4,
                AgentFeedbackLog.is_synthetic == False,  # noqa: E712
            )
        )
        result = await self.db.execute(count_stmt)
        high_quality_count = result.scalar() or 0

        if high_quality_count < MIN_EXAMPLES_FOR_SYNTHESIS:
            return

        # Don't regenerate if synthetics already exist for this agent+job combo
        existing_stmt = select(AgentFeedbackLog.id).where(
            and_(
                AgentFeedbackLog.agent_type == agent_type,
                AgentFeedbackLog.job_id == job_id,
                AgentFeedbackLog.is_synthetic == True,  # noqa: E712
            )
        ).limit(1)
        result = await self.db.execute(existing_stmt)
        if result.scalar():
            return

        await self.generate_synthetic_examples(agent_type, job_id)

    async def generate_synthetic_examples(
        self, agent_type: str, job_id: Optional[str] = None
    ):
        """Use Gemini to create varied training examples from successful patterns."""
        # Lazy import to avoid circular dependency
        from backend.services.agent_base import AIAgent

        # Fetch top-3 real templates
        stmt = (
            select(AgentFeedbackLog)
            .where(
                and_(
                    AgentFeedbackLog.agent_type == agent_type,
                    AgentFeedbackLog.rating >= 4,
                    AgentFeedbackLog.is_synthetic == False,  # noqa: E712
                )
            )
            .order_by(AgentFeedbackLog.rating.desc())
            .limit(3)
        )
        result = await self.db.execute(stmt)
        templates = list(result.scalars().all())
        if not templates:
            return

        # Optional job context
        job_context = ""
        if job_id:
            job_stmt = select(Job).where(Job.id == job_id)
            job_result = await self.db.execute(job_stmt)
            job = job_result.scalar_one_or_none()
            if job:
                job_context = (
                    f"Job Title: {job.title}\n"
                    f"Company: {job.company}\n"
                    f"Description: {(job.description or '')[:500]}"
                )

        templates_data = [
            {"input": t.input_context, "output": t.agent_output}
            for t in templates
        ]

        prompt = f"""You are an expert in {agent_type} for ATS optimization. Generate 3 diverse, high-quality synthetic training examples based on these successful templates:

Templates:
{json.dumps(templates_data, indent=2)[:3000]}

{f"Job Context: {job_context}" if job_context else ""}

Create 3 new examples that:
1. Vary the input context (different experience levels, industries, scenarios)
2. Produce outputs that follow the same quality standards but are unique
3. Maintain the same JSON structure as the templates

Return a JSON array of objects with "input_context" and "agent_output" keys."""

        try:
            import google.generativeai as genai

            model = genai.GenerativeModel(
                "gemini-1.5-flash",
                generation_config={
                    "temperature": 0.7,
                    "response_mime_type": "application/json",
                },
            )
            response = model.generate_content(prompt)
            synthetic_examples = json.loads(response.text)

            for ex in synthetic_examples[:3]:
                entry = AgentFeedbackLog(
                    agent_type=agent_type,
                    user_id=None,
                    job_id=job_id,
                    input_context=ex.get("input_context", {}),
                    agent_output=ex.get("agent_output", {}),
                    user_action="accepted",
                    rating=5,
                    is_synthetic=True,
                )
                self.db.add(entry)
            await self.db.commit()
            logger.info(
                f"[TRAINING] Generated {min(3, len(synthetic_examples))} "
                f"synthetic examples for {agent_type}"
            )
        except Exception as e:
            logger.error(f"[TRAINING] Synthetic generation failed: {e}")

    # ------------------------------------------------------------------
    # 4. PERFORMANCE METRICS
    # ------------------------------------------------------------------

    async def get_agent_performance_metrics(
        self, agent_type: str, days: int = 30
    ) -> Dict[str, Any]:
        """Calculate acceptance rate, edit distance trends, etc."""

        cutoff = datetime.utcnow() - timedelta(days=days)
        base_filter = and_(
            AgentFeedbackLog.agent_type == agent_type,
            AgentFeedbackLog.created_at >= cutoff,
        )

        total = (
            await self.db.execute(
                select(func.count(AgentFeedbackLog.id)).where(base_filter)
            )
        ).scalar() or 0

        accepted = (
            await self.db.execute(
                select(func.count(AgentFeedbackLog.id)).where(
                    and_(
                        base_filter,
                        AgentFeedbackLog.user_action.in_(["accepted", "applied"]),
                    )
                )
            )
        ).scalar() or 0

        avg_rating = (
            await self.db.execute(
                select(func.avg(AgentFeedbackLog.rating)).where(base_filter)
            )
        ).scalar() or 0

        avg_edit_distance = (
            await self.db.execute(
                select(func.avg(AgentFeedbackLog.edit_distance)).where(
                    and_(
                        base_filter,
                        AgentFeedbackLog.user_action == "edited",
                    )
                )
            )
        ).scalar() or 0

        return {
            "total_interactions": total,
            "acceptance_rate": round((accepted / max(total, 1)) * 100, 1),
            "average_rating": round(float(avg_rating), 1),
            "average_edit_distance": round(float(avg_edit_distance) * 100, 1),
            "period_days": days,
        }

    async def export_training_data(
        self, agent_type: str, min_rating: int = 4
    ) -> List[Dict]:
        """Export high-quality examples for offline fine-tuning."""

        stmt = (
            select(AgentFeedbackLog)
            .where(
                and_(
                    AgentFeedbackLog.agent_type == agent_type,
                    AgentFeedbackLog.rating >= min_rating,
                )
            )
            .order_by(AgentFeedbackLog.rating.desc())
        )
        result = await self.db.execute(stmt)
        examples = result.scalars().all()

        return [
            {
                "input": ex.input_context,
                "output": ex.agent_output,
                "rating": ex.rating,
                "is_synthetic": ex.is_synthetic,
            }
            for ex in examples
        ]

    # ------------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------------

    async def _bump_usage(self, examples: List[AgentFeedbackLog]):
        """Update last_used_at and use_count for retrieved examples."""
        now = datetime.utcnow()
        for ex in examples:
            ex.last_used_at = now
            ex.use_count = (ex.use_count or 0) + 1
        await self.db.commit()


# ======================================================================
# Utility
# ======================================================================

def _levenshtein_ratio(a: str, b: str) -> float:
    """
    Compute Levenshtein similarity ratio 0-1 without requiring python-Levenshtein.
    Falls back to difflib if the C extension is not installed.
    """
    try:
        import Levenshtein
        return Levenshtein.ratio(a, b)
    except ImportError:
        from difflib import SequenceMatcher
        return SequenceMatcher(None, a, b).ratio()

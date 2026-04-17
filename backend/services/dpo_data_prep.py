"""
DPO Training Data Preparation for the Master Orchestrator

Direct Preference Optimization requires pairs of (chosen, rejected) completions
given the same prompt/context. For the Orchestrator, this means:

  CHOSEN  = journey sequences from users who reached "applied" or "interview_secured"
  REJECTED = journey sequences from users who churned, never applied, or abandoned

This script:
  1. Queries user_journeys + job_application_outcomes to find successful vs failed journeys
  2. Pairs them by similar job description context (same role/industry)
  3. Exports DPO-formatted JSONL for fine-tuning on Together AI or any DPO trainer

Output format (TRL / HuggingFace DPO compatible):
{
    "prompt": "<user context + JD summary>",
    "chosen": "<orchestrator plan + actions from successful journey>",
    "rejected": "<orchestrator plan + actions from failed journey>"
}
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import AsyncSessionLocal

logger = logging.getLogger(__name__)

# Minimum journeys required before generating DPO pairs
MIN_JOURNEYS_FOR_DPO = 20

# Maximum age of journeys to include (freshness matters)
MAX_JOURNEY_AGE_DAYS = 180


class DPODataPreparator:
    """Prepares Direct Preference Optimization training data from user journeys."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # 1. FETCH SUCCESSFUL JOURNEYS (chosen)
    # ------------------------------------------------------------------

    async def fetch_successful_journeys(
        self,
        min_steps: int = 2,
        limit: int = 500,
    ) -> List[Dict]:
        """
        Fetch journeys where the user reached a positive outcome:
          - Marked a job as "applied"
          - Reported "interview_secured" or "offer"
          - Completed 2+ orchestrator steps
        """
        cutoff = datetime.utcnow() - timedelta(days=MAX_JOURNEY_AGE_DAYS)

        result = await self.db.execute(
            text("""
                SELECT
                    uj.id,
                    uj.user_id,
                    uj.session_id,
                    uj.journey_stage,
                    uj.action_plan,
                    uj.journey_events,
                    uj.final_response,
                    uj.steps_completed,
                    uj.overall_confidence,
                    uj.created_at,
                    jao.outcome,
                    jao.outcome_details
                FROM user_journeys uj
                LEFT JOIN job_application_outcomes jao
                    ON jao.user_id = uj.user_id
                    AND jao.journey_id = uj.id
                WHERE uj.steps_completed >= :min_steps
                  AND uj.created_at >= :cutoff
                  AND (
                      uj.journey_stage IN ('applied', 'interviewing', 'offer', 'hired')
                      OR jao.outcome IN ('applied', 'interview', 'offer', 'hired')
                  )
                ORDER BY
                    CASE jao.outcome
                        WHEN 'hired' THEN 1
                        WHEN 'offer' THEN 2
                        WHEN 'interview' THEN 3
                        WHEN 'applied' THEN 4
                        ELSE 5
                    END,
                    uj.overall_confidence DESC
                LIMIT :limit
            """),
            {"min_steps": min_steps, "cutoff": cutoff, "limit": limit},
        )
        rows = result.mappings().all()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # 2. FETCH FAILED / CHURNED JOURNEYS (rejected)
    # ------------------------------------------------------------------

    async def fetch_failed_journeys(
        self,
        limit: int = 500,
    ) -> List[Dict]:
        """
        Fetch journeys where the user churned or had negative outcomes:
          - Abandoned mid-plan (steps_failed > 0, journey_stage still "scanning")
          - Reported "rejected" outcome
          - Never returned after initial scan
        """
        cutoff = datetime.utcnow() - timedelta(days=MAX_JOURNEY_AGE_DAYS)

        result = await self.db.execute(
            text("""
                SELECT
                    uj.id,
                    uj.user_id,
                    uj.session_id,
                    uj.journey_stage,
                    uj.action_plan,
                    uj.journey_events,
                    uj.final_response,
                    uj.steps_completed,
                    uj.steps_failed,
                    uj.overall_confidence,
                    uj.created_at,
                    jao.outcome,
                    jao.outcome_details
                FROM user_journeys uj
                LEFT JOIN job_application_outcomes jao
                    ON jao.user_id = uj.user_id
                    AND jao.journey_id = uj.id
                WHERE uj.created_at >= :cutoff
                  AND (
                      uj.journey_stage IN ('new', 'scanning')
                      OR uj.steps_failed > 0
                      OR jao.outcome IN ('rejected', 'abandoned', 'ghosted')
                      -- Users who never came back after 7 days
                      OR (
                          jao.outcome IS NULL
                          AND uj.journey_stage NOT IN ('applied', 'interviewing', 'offer', 'hired')
                          AND uj.created_at < NOW() - INTERVAL '7 days'
                      )
                  )
                ORDER BY uj.created_at DESC
                LIMIT :limit
            """),
            {"cutoff": cutoff, "limit": limit},
        )
        rows = result.mappings().all()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # 3. PAIR JOURNEYS INTO DPO EXAMPLES
    # ------------------------------------------------------------------

    async def build_dpo_pairs(
        self,
        max_pairs: int = 1000,
    ) -> List[Dict]:
        """
        Build (prompt, chosen, rejected) DPO pairs from journey data.

        Pairing strategy:
          - Group by similar JD characteristics (extracted from action_plan context)
          - Each successful journey is paired with a failed journey in the same category
          - If no exact category match, pair by closest overall confidence delta
        """
        successful = await self.fetch_successful_journeys()
        failed = await self.fetch_failed_journeys()

        if len(successful) < 10 or len(failed) < 10:
            logger.warning(
                f"[DPO] Insufficient data: {len(successful)} successful, "
                f"{len(failed)} failed journeys. Need 10+ each."
            )
            return []

        pairs = []
        used_failed_ids = set()

        for success in successful:
            if len(pairs) >= max_pairs:
                break

            # Find best matching failed journey
            best_match = self._find_best_rejected_match(
                success, failed, used_failed_ids
            )
            if not best_match:
                continue

            used_failed_ids.add(best_match["id"])

            # Build the DPO triple
            prompt = self._build_prompt(success)
            chosen = self._build_completion(success)
            rejected = self._build_completion(best_match)

            pairs.append({
                "prompt": prompt,
                "chosen": chosen,
                "rejected": rejected,
                "metadata": {
                    "chosen_journey_id": str(success["id"]),
                    "rejected_journey_id": str(best_match["id"]),
                    "chosen_outcome": success.get("outcome", success.get("journey_stage")),
                    "rejected_outcome": best_match.get("outcome", best_match.get("journey_stage")),
                    "chosen_confidence": success.get("overall_confidence"),
                    "rejected_confidence": best_match.get("overall_confidence"),
                },
            })

        logger.info(f"[DPO] Built {len(pairs)} training pairs")
        return pairs

    # ------------------------------------------------------------------
    # 4. EXPORT TO JSONL
    # ------------------------------------------------------------------

    async def export_dpo_jsonl(
        self,
        output_path: str = "dpo_orchestrator_training.jsonl",
        max_pairs: int = 1000,
    ) -> Dict:
        """
        Export DPO pairs to JSONL file compatible with TRL DPOTrainer.

        Returns summary statistics.
        """
        pairs = await self.build_dpo_pairs(max_pairs)
        if not pairs:
            return {"status": "insufficient_data", "pairs": 0}

        written = 0
        with open(output_path, "w", encoding="utf-8") as f:
            for pair in pairs:
                # TRL DPOTrainer format
                record = {
                    "prompt": pair["prompt"],
                    "chosen": pair["chosen"],
                    "rejected": pair["rejected"],
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                written += 1

        stats = {
            "status": "exported",
            "pairs": written,
            "output_path": output_path,
            "avg_chosen_confidence": round(
                sum(p["metadata"]["chosen_confidence"] or 0 for p in pairs) / len(pairs), 2
            ),
            "avg_rejected_confidence": round(
                sum(p["metadata"]["rejected_confidence"] or 0 for p in pairs) / len(pairs), 2
            ),
            "outcome_distribution": self._outcome_distribution(pairs),
        }

        logger.info(f"[DPO] Exported {written} pairs to {output_path}")
        return stats

    # ------------------------------------------------------------------
    # 5. REWARD MODEL TRAINING DATA (for Phase 4)
    # ------------------------------------------------------------------

    async def export_reward_model_data(
        self,
        output_path: str = "reward_model_training.jsonl",
    ) -> Dict:
        """
        Export labeled (context, score) pairs for reward model training.

        Score mapping:
          hired:     1.0
          offer:     0.9
          interview: 0.7
          applied:   0.5
          abandoned: 0.1
          rejected:  0.2
          ghosted:   0.15
        """
        score_map = {
            "hired": 1.0,
            "offer": 0.9,
            "interview": 0.7,
            "applied": 0.5,
            "rejected": 0.2,
            "ghosted": 0.15,
            "abandoned": 0.1,
        }

        result = await self.db.execute(
            text("""
                SELECT
                    uj.action_plan,
                    uj.journey_events,
                    uj.final_response,
                    uj.overall_confidence,
                    jao.outcome
                FROM user_journeys uj
                JOIN job_application_outcomes jao
                    ON jao.user_id = uj.user_id
                    AND jao.journey_id = uj.id
                WHERE jao.outcome IS NOT NULL
                ORDER BY uj.created_at DESC
                LIMIT 5000
            """),
        )
        rows = result.mappings().all()

        written = 0
        with open(output_path, "w", encoding="utf-8") as f:
            for row in rows:
                outcome = row["outcome"]
                score = score_map.get(outcome, 0.3)

                record = {
                    "context": self._extract_context_summary(dict(row)),
                    "score": score,
                    "outcome": outcome,
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                written += 1

        return {"status": "exported", "examples": written, "output_path": output_path}

    # ------------------------------------------------------------------
    # PRIVATE HELPERS
    # ------------------------------------------------------------------

    def _find_best_rejected_match(
        self,
        success: Dict,
        failed_pool: List[Dict],
        used_ids: set,
    ) -> Optional[Dict]:
        """Find the best matching rejected journey for a successful one."""
        success_plan = self._safe_json_load(success.get("action_plan", "[]"))
        success_agents = {s.get("agent_type") for s in success_plan if isinstance(s, dict)}

        best = None
        best_score = -1

        for f in failed_pool:
            if f["id"] in used_ids:
                continue

            # Similarity score: how many agent types overlap?
            f_plan = self._safe_json_load(f.get("action_plan", "[]"))
            f_agents = {s.get("agent_type") for s in f_plan if isinstance(s, dict)}

            overlap = len(success_agents & f_agents)
            # Prefer failed journeys that attempted similar steps (makes for better contrast)
            if overlap > best_score:
                best_score = overlap
                best = f

        return best

    def _build_prompt(self, journey: Dict) -> str:
        """Extract the common context (prompt) from a journey for DPO."""
        final_resp = self._safe_json_load(journey.get("final_response", "{}"))
        events = self._safe_json_load(journey.get("journey_events", "[]"))

        # Find the decomposition event to get original context
        decomp = next(
            (e for e in events if isinstance(e, dict) and e.get("event") == "goal_decomposed"),
            None,
        )

        return (
            f"User session: {journey.get('session_id', 'unknown')}\n"
            f"Journey stage at start: {journey.get('journey_stage', 'unknown')}\n"
            f"Plan steps: {journey.get('steps_completed', 0)} completed, "
            f"{journey.get('steps_failed', 0)} failed\n"
            f"Context: {json.dumps(decomp.get('data', {}) if decomp else {}, default=str)[:500]}"
        )

    def _build_completion(self, journey: Dict) -> str:
        """Build the completion (chosen or rejected) from a journey."""
        plan = self._safe_json_load(journey.get("action_plan", "[]"))
        events = self._safe_json_load(journey.get("journey_events", "[]"))

        completion_parts = []

        # Action plan
        for step in plan:
            if isinstance(step, dict):
                completion_parts.append(
                    f"Step: {step.get('agent_type', '?')} — {step.get('goal', '?')} "
                    f"(confidence: {step.get('confidence', '?')}, status: {step.get('status', '?')})"
                )

        # Key events
        for event in events[:10]:  # Cap to 10 events
            if isinstance(event, dict):
                completion_parts.append(
                    f"Event: {event.get('event', '?')} @ {event.get('timestamp', '?')}"
                )

        return "\n".join(completion_parts) or "No plan executed."

    def _extract_context_summary(self, row: Dict) -> str:
        """Extract a concise context summary for reward model training."""
        plan = self._safe_json_load(row.get("action_plan", "[]"))
        agents = [s.get("agent_type", "?") for s in plan if isinstance(s, dict)]

        return (
            f"Agents used: {', '.join(agents)}\n"
            f"Overall confidence: {row.get('overall_confidence', 'unknown')}\n"
            f"Plan: {json.dumps(plan, default=str)[:800]}"
        )

    def _outcome_distribution(self, pairs: List[Dict]) -> Dict[str, int]:
        """Count outcome types in the paired dataset."""
        dist: Dict[str, int] = {}
        for p in pairs:
            outcome = p["metadata"].get("chosen_outcome", "unknown")
            dist[outcome] = dist.get(outcome, 0) + 1
        return dist

    @staticmethod
    def _safe_json_load(val) -> Any:
        """Safely parse JSON from string or return as-is if already parsed."""
        if isinstance(val, str):
            try:
                return json.loads(val)
            except (json.JSONDecodeError, TypeError):
                return []
        return val if val else []


# =========================================================================
# CLI ENTRY POINT — Run as: python -m backend.services.dpo_data_prep
# =========================================================================

async def main():
    """Export DPO training data from the database."""
    async with AsyncSessionLocal() as db:
        prep = DPODataPreparator(db)

        print("Exporting DPO pairs...")
        dpo_stats = await prep.export_dpo_jsonl("dpo_orchestrator_training.jsonl")
        print(f"DPO: {json.dumps(dpo_stats, indent=2)}")

        print("\nExporting reward model data...")
        rm_stats = await prep.export_reward_model_data("reward_model_training.jsonl")
        print(f"Reward Model: {json.dumps(rm_stats, indent=2)}")


if __name__ == "__main__":
    asyncio.run(main())

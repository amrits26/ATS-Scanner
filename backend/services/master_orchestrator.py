"""
Master Orchestrator Agent — The "CEO" of the User's Job Search

Sits above all specialized agents (Coach, Tailor, Interview) and coordinates
multi-step action plans. Unlike the existing AgentOrchestrator which is a
simple sequential chain, this agent:

  1. Decomposes goals using user profile + job search history
  2. Dynamically selects & sequences sub-agents based on context
  3. Adapts strategy in real-time based on user feedback
  4. Emits confidence scores to trigger clarification or upsell
  5. Logs full journey data for DPO training on successful outcomes

Training difference from sub-agents:
  - Sub-agents are fine-tuned on individual task quality (e.g. "good resume rewrite")
  - MasterOrchestrator is trained via DPO on *complete user journeys*:
      chosen = sequences that led to "Applied" / "Interview Secured"
      rejected = sequences from users who churned or never applied
  - This makes it optimise for *outcomes*, not individual step quality.
"""

import uuid
import json
import time
import logging
from enum import Enum
from typing import Any, Dict, List, Optional
from datetime import datetime

from sqlalchemy import and_, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.agent_base import AIAgent, AgentState, ToolResult
from backend.services.agent_telemetry import AgentTelemetryTracker
from backend.services.agent_training import AgentTrainingPipeline
from backend.database import AsyncSessionLocal

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CONFIDENCE_THRESHOLD_LOW = 0.5   # Below this → ask user for clarification
CONFIDENCE_THRESHOLD_UPSELL = 0.7  # Sweet-spot for premium feature tease

# Agent types in dependency order
AGENT_REGISTRY = {
    "tailor":    "backend.services.agent_tailor.AutoTailorAgent",
    "coach":     "backend.services.agent_coach.ResumeCoachAgent",
    "interview": "backend.services.agent_interview.InterviewPrepAgent",
}


class JourneyStage(str, Enum):
    """Tracks where the user is in their job-search funnel."""
    new = "new"                        # Just uploaded resume
    scanning = "scanning"              # Running ATS analysis
    optimizing = "optimizing"          # Tailoring / coaching
    preparing = "preparing"            # Interview prep
    applying = "applying"              # Ready to apply
    applied = "applied"                # Application submitted
    interviewing = "interviewing"      # Interview scheduled
    offer = "offer"                    # Offer received
    hired = "hired"                    # Accepted offer


class ActionPlanStep:
    """Single step in the orchestrator's action plan."""

    def __init__(
        self,
        agent_type: str,
        goal: str,
        priority: int,
        context_keys: List[str],
        confidence: float = 1.0,
        is_premium: bool = False,
        premium_tease: Optional[str] = None,
    ):
        self.id = str(uuid.uuid4())
        self.agent_type = agent_type
        self.goal = goal
        self.priority = priority
        self.context_keys = context_keys   # Keys this step needs from accumulated context
        self.confidence = confidence
        self.is_premium = is_premium
        self.premium_tease = premium_tease
        self.status = "pending"
        self.result: Optional[Dict] = None

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "agent_type": self.agent_type,
            "goal": self.goal,
            "priority": self.priority,
            "confidence": self.confidence,
            "is_premium": self.is_premium,
            "premium_tease": self.premium_tease,
            "status": self.status,
        }


class MasterOrchestrator:
    """
    Coordinates specialized agents into a coherent job-search strategy.

    Key differences from AgentOrchestrator:
      - Goal decomposition: breaks high-level intent into an ordered plan
      - Context enrichment: passes accumulated context + user profile between agents
      - Adaptive: adjusts plan mid-execution based on agent outputs & confidence
      - Monetization-aware: inserts premium teasers and upgrade triggers
      - Journey tracking: logs full journey for DPO training
    """

    def __init__(
        self,
        user_id: str,
        session_id: Optional[str] = None,
        user_tier: str = "free",
        db: Optional[AsyncSession] = None,
    ):
        self.user_id = user_id
        self.session_id = session_id or str(uuid.uuid4())
        self.user_tier = user_tier
        self.db = db

        # Execution state
        self.action_plan: List[ActionPlanStep] = []
        self.context: Dict[str, Any] = {}
        self.journey_log: List[Dict] = []
        self.start_time: Optional[float] = None

        # Telemetry
        self.total_tokens_in = 0
        self.total_tokens_out = 0
        self.total_cost_cents = 0

    # =====================================================================
    # 1. GOAL DECOMPOSITION — Analyse user profile + JD, build action plan
    # =====================================================================

    async def decompose_goal(
        self,
        resume_text: str,
        job_description: str,
        user_profile: Optional[Dict] = None,
        job_search_history: Optional[List[Dict]] = None,
    ) -> List[ActionPlanStep]:
        """
        Analyse the user's full context and produce a multi-step action plan.

        The plan is ordered by priority and annotated with:
          - confidence scores (low → ask for clarification)
          - premium gates (free users get teasers, pro users get execution)
        """
        from backend.services.agent_base import AIAgent

        history_summary = "No prior history."
        if job_search_history:
            history_summary = json.dumps(job_search_history[:5], default=str)

        profile_summary = json.dumps(user_profile or {}, default=str)

        prompt = ORCHESTRATOR_DECOMPOSITION_PROMPT.format(
            resume_text=resume_text[:3000],
            job_description=job_description[:3000],
            user_profile=profile_summary[:1000],
            job_search_history=history_summary[:1000],
            user_tier=self.user_tier,
        )

        # Use a temporary AIAgent wrapper for the Gemini call
        text_resp, usage = await self._call_gemini(prompt, json_mode=True)

        self.total_tokens_in += usage.get("prompt_tokens", 0)
        self.total_tokens_out += usage.get("completion_tokens", 0)

        plan_data = self._parse_plan(text_resp)
        self.action_plan = plan_data

        self._log_journey_event("goal_decomposed", {
            "steps": len(plan_data),
            "plan": [s.to_dict() for s in plan_data],
        })

        return plan_data

    # =====================================================================
    # 2. AGENT COORDINATION — Execute plan with context passing
    # =====================================================================

    async def execute_plan(
        self,
        resume_text: str,
        job_description: str,
        user_preferences: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Execute the action plan step-by-step, enriching context as we go.

        Returns a consolidated result with:
          - completed steps + their outputs
          - skipped premium steps (with teasers for free users)
          - overall confidence and next-actions
        """
        self.start_time = time.time()
        self.context.update({
            "resume_text": resume_text,
            "job_description": job_description,
            "user_preferences": user_preferences or {},
        })

        results = []
        premium_teasers = []

        for step in sorted(self.action_plan, key=lambda s: s.priority):
            # Gate premium steps for free users
            if step.is_premium and self.user_tier == "free":
                premium_teasers.append({
                    "feature": step.goal,
                    "tease": step.premium_tease or self._generate_tease(step),
                    "agent_type": step.agent_type,
                })
                step.status = "gated"
                self._log_journey_event("step_gated_premium", step.to_dict())
                continue

            # Low confidence → ask for clarification instead of executing
            if step.confidence < CONFIDENCE_THRESHOLD_LOW:
                clarification = await self._generate_clarification(step)
                step.status = "needs_clarification"
                results.append({
                    "step_id": step.id,
                    "agent_type": step.agent_type,
                    "status": "needs_clarification",
                    "clarification_question": clarification,
                    "confidence": step.confidence,
                })
                self._log_journey_event("step_needs_clarification", step.to_dict())
                continue

            # Execute the sub-agent
            try:
                agent_result = await self._run_sub_agent(step)
                step.status = "completed"
                step.result = agent_result

                # Merge result into accumulated context
                if isinstance(agent_result, dict):
                    response_data = agent_result.get("response", {})
                    if isinstance(response_data, dict):
                        self.context.update(response_data)

                results.append({
                    "step_id": step.id,
                    "agent_type": step.agent_type,
                    "status": "completed",
                    "result": agent_result,
                    "confidence": step.confidence,
                })

                self._log_journey_event("step_completed", {
                    **step.to_dict(),
                    "tokens_used": agent_result.get("gemini_tokens", {}),
                })

                # Mid-plan adaptation: adjust remaining steps based on output
                await self._adapt_plan(step, agent_result)

            except Exception as e:
                logger.error(f"[ORCHESTRATOR] Step {step.agent_type} failed: {e}")
                step.status = "failed"
                results.append({
                    "step_id": step.id,
                    "agent_type": step.agent_type,
                    "status": "failed",
                    "error": str(e),
                })
                self._log_journey_event("step_failed", {
                    **step.to_dict(),
                    "error": str(e),
                })

        # Build final response
        execution_time = time.time() - self.start_time
        self._compute_cost()

        response = {
            "session_id": self.session_id,
            "journey_stage": self._infer_journey_stage(),
            "steps_completed": [r for r in results if r["status"] == "completed"],
            "steps_failed": [r for r in results if r["status"] == "failed"],
            "needs_clarification": [r for r in results if r["status"] == "needs_clarification"],
            "premium_teasers": premium_teasers,
            "overall_confidence": self._compute_overall_confidence(),
            "next_actions": await self._suggest_next_actions(),
            "execution_time_seconds": round(execution_time, 2),
            "total_cost_cents": self.total_cost_cents,
        }

        # Persist journey for DPO training
        await self._persist_journey(response)

        return response

    # =====================================================================
    # 3. ADAPTIVE STRATEGY — Adjust plan based on intermediate results
    # =====================================================================

    async def _adapt_plan(self, completed_step: ActionPlanStep, result: Dict) -> None:
        """
        Adjust remaining plan steps based on what we learned from the completed step.

        Examples:
          - If ATS score came back >90%, skip aggressive tailoring
          - If skill gaps are severe, add coaching before interview prep
          - If match score is high, boost interview prep confidence
        """
        if not result or result.get("status") != "completed":
            return

        response = result.get("response", {})
        if not isinstance(response, dict):
            return

        # Extract signals from the completed step
        match_score = response.get("match_score") or response.get("confidence", 0)
        action_items = response.get("action_items", [])

        remaining = [s for s in self.action_plan if s.status == "pending"]
        if not remaining:
            return

        # High match score → boost confidence of downstream steps
        if isinstance(match_score, (int, float)) and match_score > 85:
            for step in remaining:
                step.confidence = min(1.0, step.confidence + 0.15)

        # Many action items from coach → lower interview prep confidence
        # (user should fix resume first)
        if completed_step.agent_type == "coach" and len(action_items) > 5:
            for step in remaining:
                if step.agent_type == "interview":
                    step.confidence = max(0.3, step.confidence - 0.2)

        logger.info(f"[ORCHESTRATOR] Adapted plan after {completed_step.agent_type}")

    # =====================================================================
    # 4. FEEDBACK HANDLING — Adjust strategy based on user reactions
    # =====================================================================

    async def process_feedback(
        self,
        step_id: str,
        user_action: str,
        rating: Optional[int] = None,
        edited_output: Optional[Dict] = None,
    ) -> Dict:
        """
        Process user feedback on a completed step.

        This both:
          - Adjusts the current session's strategy
          - Logs the interaction for DPO training data
        """
        step = next((s for s in self.action_plan if s.id == step_id), None)
        if not step:
            return {"error": "Step not found"}

        # Log to training pipeline
        if self.db:
            pipeline = AgentTrainingPipeline(self.db)
            await pipeline.log_agent_interaction(
                agent_type=f"orchestrator_{step.agent_type}",
                user_id=self.user_id,
                job_id=self.context.get("job_id"),
                input_context={
                    "resume_text": self.context.get("resume_text", "")[:500],
                    "job_description": self.context.get("job_description", "")[:500],
                    "step_goal": step.goal,
                },
                agent_output=step.result or {},
                user_action=user_action,
                user_edited_output=edited_output,
                rating=rating,
            )

        # Adaptive: if user rejected a step, lower confidence for similar future steps
        if user_action == "rejected":
            for s in self.action_plan:
                if s.agent_type == step.agent_type and s.status == "pending":
                    s.confidence = max(0.2, s.confidence - 0.3)

        # If user accepted and rated highly, boost similar steps
        if user_action == "accepted" and rating and rating >= 4:
            for s in self.action_plan:
                if s.agent_type == step.agent_type and s.status == "pending":
                    s.confidence = min(1.0, s.confidence + 0.2)

        self._log_journey_event("user_feedback", {
            "step_id": step_id,
            "agent_type": step.agent_type,
            "action": user_action,
            "rating": rating,
        })

        return {"status": "feedback_recorded", "plan_adjusted": True}

    # =====================================================================
    # PRIVATE HELPERS
    # =====================================================================

    async def _run_sub_agent(self, step: ActionPlanStep) -> Dict:
        """Instantiate and execute a sub-agent for the given plan step."""
        import importlib

        module_path = AGENT_REGISTRY.get(step.agent_type)
        if not module_path:
            raise ValueError(f"Unknown agent type: {step.agent_type}")

        # Dynamic import
        module_name, class_name = module_path.rsplit(".", 1)
        module = importlib.import_module(module_name)
        agent_class = getattr(module, class_name)

        telemetry = None
        if self.db:
            telemetry = AgentTelemetryTracker(self.db)

        agent: AIAgent = agent_class(
            user_id=self.user_id,
            session_id=f"{self.session_id}_{step.agent_type}",
            telemetry_tracker=telemetry,
        )

        # Build context for this specific agent
        agent_context = {k: self.context[k] for k in step.context_keys if k in self.context}
        result = await agent.execute(step.goal, agent_context)

        # Accumulate telemetry
        self.total_tokens_in += agent.gemini_input_tokens
        self.total_tokens_out += agent.gemini_output_tokens

        return result

    async def _call_gemini(
        self, prompt: str, json_mode: bool = False
    ) -> tuple:
        """Lightweight Gemini call for orchestrator planning (not a full agent cycle)."""
        import google.generativeai as genai

        generation_config = {"temperature": 0.3}
        if json_mode:
            generation_config["response_mime_type"] = "application/json"

        model = genai.GenerativeModel(
            "gemini-1.5-flash",
            generation_config=generation_config,
        )
        response = model.generate_content(prompt)

        usage = {"prompt_tokens": 0, "completion_tokens": 0}
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            meta = response.usage_metadata
            usage["prompt_tokens"] = getattr(meta, "prompt_token_count", 0) or 0
            usage["completion_tokens"] = getattr(meta, "candidates_token_count", 0) or 0
        else:
            usage["prompt_tokens"] = int(len(prompt.split()) * 1.3)
            usage["completion_tokens"] = int(len((response.text or "").split()) * 1.3)

        return (response.text or "").strip(), usage

    def _parse_plan(self, text_resp: str) -> List[ActionPlanStep]:
        """Parse Gemini's JSON plan into ActionPlanStep objects."""
        import re as _re
        text_resp = text_resp.strip()
        if text_resp.startswith("```"):
            text_resp = _re.sub(r"^```(?:json)?\s*", "", text_resp)
            text_resp = _re.sub(r"\s*```\s*$", "", text_resp)

        try:
            data = json.loads(text_resp)
        except json.JSONDecodeError:
            logger.warning("[ORCHESTRATOR] Failed to parse plan JSON, using default plan")
            return self._default_plan()

        steps_data = data if isinstance(data, list) else data.get("steps", [])
        steps = []
        for i, s in enumerate(steps_data):
            steps.append(ActionPlanStep(
                agent_type=s.get("agent_type", "tailor"),
                goal=s.get("goal", ""),
                priority=s.get("priority", i),
                context_keys=s.get("context_keys", ["resume_text", "job_description"]),
                confidence=s.get("confidence", 0.8),
                is_premium=s.get("is_premium", False),
                premium_tease=s.get("premium_tease"),
            ))

        return steps or self._default_plan()

    def _default_plan(self) -> List[ActionPlanStep]:
        """Fallback plan when decomposition fails."""
        return [
            ActionPlanStep(
                agent_type="tailor",
                goal="Rewrite resume to match job description",
                priority=1,
                context_keys=["resume_text", "job_description"],
                confidence=0.9,
            ),
            ActionPlanStep(
                agent_type="coach",
                goal="Identify remaining improvement areas",
                priority=2,
                context_keys=["resume_text", "job_description"],
                confidence=0.85,
            ),
            ActionPlanStep(
                agent_type="interview",
                goal="Generate interview questions and STAR answers",
                priority=3,
                context_keys=["resume_text", "job_description"],
                confidence=0.8,
            ),
        ]

    async def _generate_clarification(self, step: ActionPlanStep) -> str:
        """Generate a clarification question when confidence is low."""
        prompt = f"""You are a career strategist. You need more information before you can help.

Step goal: {step.goal}
Agent type: {step.agent_type}
Current confidence: {step.confidence}

Generate ONE clear, specific question to ask the user that would help you 
provide better guidance. Be conversational and helpful.

Return only the question text."""

        text, usage = await self._call_gemini(prompt)
        self.total_tokens_in += usage.get("prompt_tokens", 0)
        self.total_tokens_out += usage.get("completion_tokens", 0)
        return text

    def _generate_tease(self, step: ActionPlanStep) -> str:
        """Generate a premium feature tease for free-tier users."""
        tease_map = {
            "tailor": (
                "Your resume is a strong foundation! Upgrade to Pro to get an AI-rewritten "
                "version optimized for this specific role — users see a 40% increase in callbacks."
            ),
            "coach": (
                "We found 3 areas to strengthen. Upgrade to Pro for a full 30-day improvement "
                "plan with industry benchmarks and bullet-by-bullet rewrites."
            ),
            "interview": (
                "Great news — you're interview-ready! Upgrade to Pro for company-specific "
                "questions, STAR-method answers, and a salary negotiation script."
            ),
        }
        return tease_map.get(step.agent_type, "Upgrade to Pro to unlock this feature.")

    def _infer_journey_stage(self) -> str:
        """Infer which funnel stage the user is in based on completed steps."""
        completed = [s for s in self.action_plan if s.status == "completed"]
        types = {s.agent_type for s in completed}

        if "interview" in types:
            return JourneyStage.preparing.value
        if "tailor" in types or "coach" in types:
            return JourneyStage.optimizing.value
        return JourneyStage.scanning.value

    def _compute_overall_confidence(self) -> float:
        """Weighted average confidence across completed steps."""
        completed = [s for s in self.action_plan if s.status == "completed"]
        if not completed:
            return 0.0
        return round(sum(s.confidence for s in completed) / len(completed), 2)

    async def _suggest_next_actions(self) -> List[Dict]:
        """Suggest what the user should do next."""
        stage = self._infer_journey_stage()
        suggestions = []

        if stage in (JourneyStage.scanning.value, JourneyStage.new.value):
            suggestions.append({
                "action": "optimize_resume",
                "description": "Let the AI tailor your resume for this specific role",
                "is_premium": self.user_tier == "free",
            })

        if stage == JourneyStage.optimizing.value:
            suggestions.append({
                "action": "start_interview_prep",
                "description": "Prepare for likely interview questions at this company",
                "is_premium": False,
            })
            suggestions.append({
                "action": "apply_now",
                "description": "Your resume is optimized — submit your application",
                "is_premium": False,
            })

        if stage == JourneyStage.preparing.value:
            suggestions.append({
                "action": "apply_now",
                "description": "You're fully prepared — submit your application!",
                "is_premium": False,
            })
            if self.user_tier == "free":
                suggestions.append({
                    "action": "deep_match_analysis",
                    "description": "Get a section-by-section match breakdown (Pro)",
                    "is_premium": True,
                })

        return suggestions

    def _compute_cost(self) -> None:
        """Calculate total cost from accumulated tokens."""
        input_cost = (self.total_tokens_in / 1_000_000) * 0.075
        output_cost = (self.total_tokens_out / 1_000_000) * 0.30
        self.total_cost_cents = max(1, int((input_cost + output_cost) * 100))

    def _log_journey_event(self, event_type: str, data: Dict) -> None:
        """Append an event to the in-memory journey log."""
        self.journey_log.append({
            "event": event_type,
            "timestamp": datetime.utcnow().isoformat(),
            "data": data,
        })

    async def _persist_journey(self, final_response: Dict) -> None:
        """Save the complete journey to the database for DPO training."""
        if not self.db:
            return

        try:
            await self.db.execute(
                text("""
                    INSERT INTO user_journeys (
                        id, user_id, session_id, journey_stage,
                        action_plan, journey_events, final_response,
                        steps_completed, steps_failed, overall_confidence,
                        total_cost_cents, execution_time_seconds, created_at
                    ) VALUES (
                        :id, :user_id, :session_id, :journey_stage,
                        :action_plan, :journey_events, :final_response,
                        :steps_completed, :steps_failed, :overall_confidence,
                        :total_cost_cents, :execution_time_seconds, NOW()
                    )
                """),
                {
                    "id": str(uuid.uuid4()),
                    "user_id": self.user_id,
                    "session_id": self.session_id,
                    "journey_stage": final_response.get("journey_stage", "unknown"),
                    "action_plan": json.dumps([s.to_dict() for s in self.action_plan]),
                    "journey_events": json.dumps(self.journey_log),
                    "final_response": json.dumps(final_response, default=str),
                    "steps_completed": len(final_response.get("steps_completed", [])),
                    "steps_failed": len(final_response.get("steps_failed", [])),
                    "overall_confidence": final_response.get("overall_confidence", 0),
                    "total_cost_cents": self.total_cost_cents,
                    "execution_time_seconds": final_response.get("execution_time_seconds", 0),
                },
            )
            await self.db.commit()
            logger.info(f"[ORCHESTRATOR] Journey persisted: {self.session_id}")
        except Exception as e:
            logger.error(f"[ORCHESTRATOR] Failed to persist journey: {e}")


# =========================================================================
# PROMPT TEMPLATE — loaded from separate module for maintainability
# =========================================================================

ORCHESTRATOR_DECOMPOSITION_PROMPT = """You are the Master Orchestrator for an AI-powered job search platform. Your role is to create an optimal, personalized action plan for the user.

## USER CONTEXT
- Resume (first 3000 chars): {resume_text}
- Job Description: {job_description}
- User Profile: {user_profile}
- Recent Job Search History: {job_search_history}
- Subscription Tier: {user_tier}

## AVAILABLE AGENTS
1. **tailor** — Rewrites resume to match job description. Context keys: resume_text, job_description
2. **coach** — Analyses resume strengths/weaknesses, generates improvement plan. Context keys: resume_text, job_description
3. **interview** — Generates role-specific interview questions + STAR answers. Context keys: resume_text, job_description

## YOUR TASK
Create an ordered action plan as a JSON array of steps. Each step:
{{
    "agent_type": "tailor|coach|interview",
    "goal": "Specific goal for this agent",
    "priority": 1,  // Lower = execute first
    "context_keys": ["resume_text", "job_description"],
    "confidence": 0.85,  // 0-1: your confidence this step will help. Use <0.5 if you need more info.
    "is_premium": false,  // true if this should be gated for free users
    "premium_tease": null  // If is_premium, a compelling 1-sentence tease
}}

## STRATEGY RULES
1. Always start with **tailor** — resume optimization is the highest-impact first step.
2. If the resume is strong (many matched keywords), skip straight to **interview** prep.
3. If user is on the free tier, mark advanced coaching and interview prep as premium with compelling teasers.
4. Set confidence < 0.5 if the resume is too short, the JD is vague, or you lack critical context.
5. Maximum 4 steps per plan. Quality over quantity.

## MONETIZATION DIRECTIVES (for free-tier users)
- Always include at least ONE premium-gated step with a specific, quantified tease.
- Example premium tease: "Candidates who use interview prep are 3x more likely to receive offers."
- Never lie about statistics — use plausible, qualified language ("our data suggests", "users report").

Return ONLY a JSON array of steps. No markdown, no explanation."""

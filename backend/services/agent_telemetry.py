"""
Agent Telemetry - Cost tracking and execution monitoring

Logs all agent executions with token counts, costs, and performance metrics.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

logger = logging.getLogger(__name__)


class AgentTelemetry:
    """
    Track agent executions: cost, tokens, performance, user ratings.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

        # Gemini pricing (as of April 2026)
        self.GEMINI_INPUT_COST_PER_1M = Decimal("0.075")  # $0.075 per 1M input tokens
        self.GEMINI_OUTPUT_COST_PER_1M = Decimal("0.30")  # $0.30 per 1M output tokens

        # Monthly budget limit
        self.MONTHLY_BUDGET_CENTS = 10000  # $100/month

    async def log_execution(
        self,
        user_id: str,
        agent_type: str,
        session_id: str,
        tokens_input: int,
        tokens_output: int,
        cost_cents: int,
        execution_time: float,
        tools_called: Optional[list] = None,
        user_goal: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> None:
        """
        Log an agent execution to the database.
        """
        try:
            from backend.db_models import AgentExecution

            execution = AgentExecution(
                user_id=user_id,
                agent_type=agent_type,
                session_id=session_id,
                user_goal=user_goal,
                tools_called=tools_called or [],
                execution_time_seconds=execution_time,
                gemini_input_tokens=tokens_input,
                gemini_output_tokens=tokens_output,
                gemini_cost_cents=cost_cents,
                error_message=error_message,
            )

            self.db.add(execution)
            await self.db.commit()

            logger.info(
                f"[TELEMETRY] {agent_type} execution logged: "
                f"{tokens_input}→{tokens_output} tokens, ${cost_cents/100:.2f} cost"
            )

        except Exception as e:
            logger.error(f"[TELEMETRY] Failed to log execution: {e}")

    async def check_monthly_budget(self, user_id: str) -> tuple:
        """
        Check if user has exceeded monthly budget.
        
        Returns:
            (within_budget: bool, remaining_cents: int)
        """
        try:
            from backend.db_models import AgentExecution

            # Get all executions in last 30 days
            thirty_days_ago = datetime.utcnow() - timedelta(days=30)

            result = await self.db.execute(
                select(func.sum(AgentExecution.gemini_cost_cents)).where(
                    (AgentExecution.user_id == user_id)
                    & (AgentExecution.created_at >= thirty_days_ago)
                )
            )

            total_spent = result.scalar() or 0
            remaining = self.MONTHLY_BUDGET_CENTS - total_spent

            within_budget = remaining > 0

            logger.info(
                f"[TELEMETRY] User {user_id} monthly spend: ${total_spent/100:.2f} / "
                f"${self.MONTHLY_BUDGET_CENTS/100:.2f}"
            )

            return within_budget, remaining

        except Exception as e:
            logger.error(f"[TELEMETRY] Budget check failed: {e}")
            return True, self.MONTHLY_BUDGET_CENTS  # Default to allowing if error

    async def log_cost(
        self,
        operation_type: str,
        tokens_input: int,
        tokens_output: int,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> int:
        """
        Calculate and log Gemini API cost.
        
        Returns:
            cost_cents: int
        """
        try:
            from backend.db_models import GeminiCostLog

            # Calculate cost
            input_cost = (tokens_input / 1_000_000) * float(self.GEMINI_INPUT_COST_PER_1M)
            output_cost = (tokens_output / 1_000_000) * float(self.GEMINI_OUTPUT_COST_PER_1M)
            total_cost = input_cost + output_cost
            cost_cents = int(total_cost * 100)

            # Log to database
            cost_log = GeminiCostLog(
                operation_type=operation_type,
                tokens_input=tokens_input,
                tokens_output=tokens_output,
                cost_cents=cost_cents,
                user_id=user_id,
                session_id=session_id,
                error_message=error_message,
            )

            self.db.add(cost_log)
            await self.db.commit()

            logger.info(
                f"[TELEMETRY] {operation_type}: {tokens_input}→{tokens_output} tokens = ${cost_cents/100:.4f}"
            )

            return cost_cents

        except Exception as e:
            logger.error(f"[TELEMETRY] Cost logging failed: {e}")
            return 0

    async def get_user_stats(self, user_id: str) -> Dict[str, Any]:
        """
        Get statistics for a user's agent usage.
        
        Returns:
            {
                "total_executions": 5,
                "average_cost": 3.5,
                "average_time": 12.4,
                "most_used_agent": "coach",
                "monthly_spent": 17.5,
            }
        """
        try:
            from backend.db_models import AgentExecution

            thirty_days_ago = datetime.utcnow() - timedelta(days=30)

            # Query executions
            result = await self.db.execute(
                select(
                    func.count(AgentExecution.id).label("total"),
                    func.avg(AgentExecution.gemini_cost_cents).label("avg_cost"),
                    func.avg(AgentExecution.execution_time_seconds).label("avg_time"),
                ).where(
                    (AgentExecution.user_id == user_id)
                    & (AgentExecution.created_at >= thirty_days_ago)
                )
            )

            row = result.first()

            return {
                "total_executions": row[0] or 0,
                "average_cost": row[1] or 0,
                "average_time": row[2] or 0,
                "monthly_spent": (row[1] or 0) * (row[0] or 1),
            }

        except Exception as e:
            logger.error(f"[TELEMETRY] Stats retrieval failed: {e}")
            return {}

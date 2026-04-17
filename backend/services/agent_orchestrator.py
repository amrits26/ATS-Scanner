"""
Agent Orchestrator – Chain multiple AIAgent instances in sequence.

Usage:
    orchestrator = AgentOrchestrator([gap_agent, tailor_agent])
    result = await orchestrator.run(initial_context)
"""

import logging
from typing import List, Any, Dict, Optional

from backend.services.agent_base import AIAgent

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """
    Chains a list of AIAgent instances sequentially.
    The output dict from agent N is merged into the input context for agent N+1.
    """

    def __init__(self, agents: List[AIAgent]):
        self.agents = agents

    async def run(self, initial_context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute all agents in sequence.

        Returns the accumulated context dict after all agents complete.
        """
        context = dict(initial_context)
        for agent in self.agents:
            logger.info(f"[Orchestrator] Running agent: {agent.agent_type}")
            try:
                goal = context.pop("_goal", f"Execute {agent.agent_type}")
                result = await agent.execute(goal, context)
                if isinstance(result, dict):
                    context.update(result)
                else:
                    context[f"{agent.agent_type}_result"] = result
            except Exception as e:
                logger.error(f"[Orchestrator] Agent {agent.agent_type} failed: {e}")
                context[f"{agent.agent_type}_error"] = str(e)
        return context

    async def run_until(
        self, stop_agent_type: str, initial_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute agents until we reach (and include) the agent with the given type.
        Useful for multi-call interactive flows (e.g. get questions, then submit answers).
        """
        context = dict(initial_context)
        for agent in self.agents:
            logger.info(f"[Orchestrator] Running agent: {agent.agent_type}")
            try:
                goal = context.pop("_goal", f"Execute {agent.agent_type}")
                result = await agent.execute(goal, context)
                if isinstance(result, dict):
                    context.update(result)
                else:
                    context[f"{agent.agent_type}_result"] = result
            except Exception as e:
                logger.error(f"[Orchestrator] Agent {agent.agent_type} failed: {e}")
                context[f"{agent.agent_type}_error"] = str(e)

            if agent.agent_type == stop_agent_type:
                break
        return context

"""
Agent Base Class - Foundation for all AI agents

Implements: Think → Act → Reflect cycle
- Think: Use Gemini to decide which tools to call
- Act: Execute tools in order
- Reflect: Synthesize results into user response
"""

import uuid
import logging
import asyncio
import time
from enum import Enum
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, Callable
from datetime import datetime

import google.generativeai as genai

logger = logging.getLogger(__name__)


class AgentState(str, Enum):
    """Agent execution states"""
    idle = "idle"
    thinking = "thinking"
    acting = "acting"
    reflecting = "reflecting"
    completed = "completed"
    failed = "failed"


class ToolResult:
    """Result of a tool execution"""

    def __init__(self, tool_name: str, success: bool, result: Any, error: str = None):
        self.tool_name = tool_name
        self.success = success
        self.result = result
        self.error = error


class AIAgent(ABC):
    """
    Base class for all AI agents.
    
    Subclasses must implement:
    - register_tools(): Return dict of tool functions
    - parse_user_goal(): Extract user intent
    """

    def __init__(
        self,
        agent_type: str,
        user_id: str,
        session_id: str = None,
        telemetry_tracker=None,
    ):
        self.agent_type = agent_type  # 'coach', 'tailor', 'interview'
        self.user_id = user_id
        self.session_id = session_id or str(uuid.uuid4())
        self.state = AgentState.idle
        self.start_time = None
        self.end_time = None

        # Telemetry
        self.telemetry = telemetry_tracker
        self.gemini_input_tokens = 0
        self.gemini_output_tokens = 0

        # Tool registry
        self.tools = {}
        self._register_tools()

    # ========================================================================
    # Abstract methods (implemented by subclasses)
    # ========================================================================

    @abstractmethod
    def _register_tools(self) -> None:
        """
        Subclasses must populate self.tools dict:
        self.tools = {
            "strength_analyzer": self._strength_analyzer,
            "gap_detector": self._gap_detector,
            ...
        }
        """
        pass

    @abstractmethod
    async def parse_user_goal(self, query: str) -> Dict[str, Any]:
        """
        Use Gemini to parse user's natural language query into structured intent.
        
        Returns:
            {
                "goal": "improve resume bullets",
                "context": {"resume": "...", "target_role": "..."},
                "required_tools": ["strength_analyzer", "bullet_rewriter"],
            }
        """
        pass

    # ========================================================================
    # THINK PHASE: Decide which tools to call
    # ========================================================================

    async def think(self, user_goal: str, context: Dict[str, Any]) -> List[Dict]:
        """
        Use Gemini to decide: What tools should I call in what order?
        
        Returns:
            [
                {"tool": "strength_analyzer", "args": {...}},
                {"tool": "bullet_rewriter", "args": {...}},
                ...
            ]
        """
        self.state = AgentState.thinking
        logger.info(f"[{self.agent_type}] THINK: Analyzing user goal...")

        try:
            # Prepare tool descriptions for Gemini
            tool_descriptions = self._get_tool_descriptions()

            prompt = f"""You are an AI agent tasked with helping the user achieve their goal.

User Goal: {user_goal}

Context: {context}

Available Tools:
{tool_descriptions}

Your task: Decide which tools to call and in what order to accomplish the user's goal.
Return a JSON list of tool calls:
[
  {{"tool": "tool_name", "args": {{"param1": "value1", ...}}}},
  ...
]

Return ONLY the JSON, no other text."""

            model = genai.GenerativeModel("gemini-1.5-flash")
            response = model.generate_content(prompt)

            # Track token usage
            self.gemini_input_tokens += len(prompt.split())
            self.gemini_output_tokens += len(response.text.split())

            # Parse tool calls
            tool_calls = self._parse_tool_calls_json(response.text)
            logger.info(f"[{self.agent_type}] THINK: Decided to call {len(tool_calls)} tools")
            return tool_calls

        except Exception as e:
            logger.error(f"[{self.agent_type}] THINK failed: {e}")
            self.state = AgentState.failed
            raise

    # ========================================================================
    # ACT PHASE: Execute tools
    # ========================================================================

    async def act(self, tool_calls: List[Dict]) -> List[ToolResult]:
        """
        Execute each tool call in sequence.
        
        Returns:
            [ToolResult(...), ToolResult(...), ...]
        """
        self.state = AgentState.acting
        logger.info(f"[{self.agent_type}] ACT: Executing {len(tool_calls)} tools...")

        results = []
        for i, tool_call in enumerate(tool_calls, 1):
            try:
                tool_name = tool_call.get("tool")
                tool_args = tool_call.get("args", {})

                if tool_name not in self.tools:
                    results.append(
                        ToolResult(
                            tool_name,
                            False,
                            None,
                            f"Tool '{tool_name}' not found",
                        )
                    )
                    continue

                logger.info(
                    f"[{self.agent_type}] ACT: Calling tool {i}/{len(tool_calls)}: {tool_name}"
                )

                # Execute tool
                tool_func = self.tools[tool_name]
                try:
                    # Try async, fall back to sync
                    if asyncio.iscoroutinefunction(tool_func):
                        result = await tool_func(**tool_args)
                    else:
                        result = tool_func(**tool_args)

                    results.append(ToolResult(tool_name, True, result))
                except Exception as tool_error:
                    logger.error(f"[{self.agent_type}] Tool {tool_name} failed: {tool_error}")
                    results.append(
                        ToolResult(tool_name, False, None, str(tool_error))
                    )

            except Exception as e:
                logger.error(f"[{self.agent_type}] ACT failed on tool {i}: {e}")

        return results

    # ========================================================================
    # REFLECT PHASE: Synthesize results into response
    # ========================================================================

    async def reflect(
        self, user_goal: str, tool_results: List[ToolResult]
    ) -> Dict[str, Any]:
        """
        Use Gemini to synthesize tool results into a cohesive user response.
        
        Returns:
            {
                "response": "Here's what I found...",
                "action_items": [...],
                "confidence": 0.95,
                "follow_up": "Next step is..."
            }
        """
        self.state = AgentState.reflecting
        logger.info(f"[{self.agent_type}] REFLECT: Synthesizing results...")

        try:
            # Format tool results for Gemini
            results_text = "\n".join(
                [
                    f"- {r.tool_name}: {'✓ ' + str(r.result)[:200] if r.success else '✗ ' + r.error}"
                    for r in tool_results
                ]
            )

            prompt = f"""You are synthesizing tool results to answer the user's goal.

User Goal: {user_goal}

Tool Results:
{results_text}

Your task: Create a comprehensive, actionable response for the user based on these results.
Include:
1. Main findings
2. Specific action items (if any)
3. Next steps
4. Confidence level (0-100)

Return JSON with keys: response, action_items, confidence, follow_up"""

            model = genai.GenerativeModel("gemini-1.5-flash")
            response = model.generate_content(prompt)

            # Track tokens
            self.gemini_input_tokens += len(prompt.split())
            self.gemini_output_tokens += len(response.text.split())

            synthesis = self._parse_synthesis_json(response.text)
            self.state = AgentState.completed

            logger.info(f"[{self.agent_type}] REFLECT: Complete")
            return synthesis

        except Exception as e:
            logger.error(f"[{self.agent_type}] REFLECT failed: {e}")
            self.state = AgentState.failed
            raise

    # ========================================================================
    # ORCHESTRATION: Run full Think → Act → Reflect cycle
    # ========================================================================

    async def execute(self, user_goal: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute full agent cycle: Think → Act → Reflect.
        
        Returns:
            {
                "session_id": uuid,
                "status": "completed",
                "response": {...},
                "execution_time_seconds": 12.4,
                "gemini_tokens": {"input": 2000, "output": 1500},
                "gemini_cost_cents": 3.5
            }
        """
        self.start_time = time.time()

        try:
            # THINK
            tool_calls = await self.think(user_goal, context)

            # ACT
            tool_results = await self.act(tool_calls)

            # REFLECT
            synthesis = await self.reflect(user_goal, tool_results)

            # Calculate elapsed time and cost
            self.end_time = time.time()
            execution_time = self.end_time - self.start_time

            # Estimate Gemini cost
            # Pricing: $0.075/1M tokens input, $0.30/1M tokens output
            input_cost = (self.gemini_input_tokens / 1_000_000) * 0.075
            output_cost = (self.gemini_output_tokens / 1_000_000) * 0.30
            total_cost_cents = int((input_cost + output_cost) * 100)

            # Log to telemetry if available
            if self.telemetry:
                await self.telemetry.log_execution(
                    user_id=self.user_id,
                    agent_type=self.agent_type,
                    session_id=self.session_id,
                    tokens_input=self.gemini_input_tokens,
                    tokens_output=self.gemini_output_tokens,
                    cost_cents=total_cost_cents,
                    execution_time=execution_time,
                )

            return {
                "session_id": self.session_id,
                "status": "completed",
                "response": synthesis,
                "execution_time_seconds": round(execution_time, 2),
                "gemini_tokens": {
                    "input": self.gemini_input_tokens,
                    "output": self.gemini_output_tokens,
                },
                "gemini_cost_cents": total_cost_cents,
            }

        except Exception as e:
            logger.error(f"[{self.agent_type}] Execution failed: {e}")
            self.state = AgentState.failed
            return {
                "session_id": self.session_id,
                "status": "failed",
                "error": str(e),
                "execution_time_seconds": time.time() - self.start_time,
            }

    # ========================================================================
    # HELPER METHODS
    # ========================================================================

    def _get_tool_descriptions(self) -> str:
        """Generate natural language descriptions of available tools"""
        descriptions = []
        for tool_name, tool_func in self.tools.items():
            docstring = tool_func.__doc__ or "No description"
            descriptions.append(f"- {tool_name}: {docstring}")
        return "\n".join(descriptions)

    def _parse_tool_calls_json(self, text: str) -> List[Dict]:
        """
        Parse Gemini response to extract tool calls.
        Handles malformed JSON gracefully.
        """
        import json
        import re

        # Try to extract JSON from response
        try:
            # Look for JSON array pattern
            json_match = re.search(r"\[.*\]", text, re.DOTALL)
            if json_match:
                json_str = json_match.group()
                return json.loads(json_str)
        except:
            pass

        logger.warning(f"[{self.agent_type}] Failed to parse tool calls JSON")
        return []

    def _parse_synthesis_json(self, text: str) -> Dict:
        """
        Parse Gemini synthesis response.
        Handles malformed JSON gracefully.
        """
        import json

        try:
            # Extract JSON from response
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                json_str = text[start:end]
                return json.loads(json_str)
        except:
            pass

        # Fallback
        return {
            "response": text,
            "action_items": [],
            "confidence": 50,
            "follow_up": "Let me help you further.",
        }

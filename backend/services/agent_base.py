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

import json as json_module
import re

import google.generativeai as genai

logger = logging.getLogger(__name__)


# ============================================================================
# Shared tech acronym whitelist — skills that look like short/junk tokens but
# are legitimate. Imported by jd_analyzer.py and keyword_heatmap.py.
# ============================================================================
TECH_ACRONYM_WHITELIST: set[str] = {
    "ai", "ml", "qa", "ui", "ux", "c#", "c++", "go", "r",
    "api", "aws", "gcp", "sql", "csv", "rpa", "dba",
    "ci", "cd", "ci/cd", "rest", "sdk", "iot", "vpn",
    "dns", "ssh", "tls", "ssl", "tcp", "ip",
    "saas", "paas", "iaas", "crm", "erp", "etl",
    "nlp", "llm", "rag", "ocr", "rnn", "cnn", "gan",
    "vue", "php", "seo", "sem", "bi", "kpi", "okr",
    "jwt", "oauth", "sso", "rbac", "gdpr", "pci",
    "k8s", "ec2", "s3", "rds", "ecs", "eks", "iam",
    "sqs", "sns", "cdn", "waf", "emr", "glue",
    "gke", "bq", "gcr", "gcs",
    "vm", "aks", "adf",
    "nos", "npm", "pip", "gem", "mvn", "nix",
}


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

    # Task-type temperature defaults
    TEMPERATURE_SCORING = 0.1   # Deterministic: scoring, extraction, grading
    TEMPERATURE_CREATIVE = 0.7  # Creative: rewriting, cover letters, coaching

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
    # CENTRALIZED GEMINI CALL — temperature, JSON mode, real token counting
    # ========================================================================

    async def call_gemini(
        self,
        prompt: str,
        *,
        temperature: float = None,
        json_mode: bool = False,
        model_name: str = "gemini-1.5-flash",
        use_few_shot: bool = False,
        input_context: dict = None,
        prefer_fine_tuned: bool = True,
    ) -> tuple[str, dict]:
        """
        Centralized Gemini API call with:
        - Configurable temperature (defaults by task type)
        - Optional JSON response mode for structured output
        - Real token counting via usage_metadata (not word count)
        - Optional few-shot prompt augmentation from training pipeline
        - Fine-tuned model routing via Together AI when deployed
        
        Returns:
            (response_text, usage_dict)
            usage_dict = {"prompt_tokens": int, "completion_tokens": int}
        """
        # Optionally inject few-shot examples from training pipeline
        if use_few_shot and input_context:
            try:
                from backend.services.agent_training import AgentTrainingPipeline
                from backend.database import AsyncSessionLocal

                async with AsyncSessionLocal() as db:
                    pipeline = AgentTrainingPipeline(db)
                    prompt = await pipeline.build_few_shot_prompt(
                        self.agent_type,
                        input_context,
                        prompt,
                        max_examples=2,
                    )
            except Exception as e:
                logger.warning(f"[{self.agent_type.upper()}] Few-shot injection failed: {e}")

        if temperature is None:
            temperature = self.TEMPERATURE_SCORING

        # Check for a deployed fine-tuned model
        if prefer_fine_tuned and self.agent_type:
            try:
                from backend.services.fine_tuning import FineTuningService
                from backend.database import AsyncSessionLocal as _ASL

                async with _ASL() as ft_db:
                    ft_model_id = await FineTuningService(ft_db).get_active_model(
                        self.agent_type
                    )
                if ft_model_id:
                    logger.info(
                        f"[{self.agent_type.upper()}] Routing to fine-tuned model: {ft_model_id}"
                    )
                    return await self._call_together_model(
                        ft_model_id, prompt, temperature, json_mode
                    )
            except Exception as e:
                logger.warning(
                    f"[{self.agent_type.upper()}] Fine-tuned lookup failed, "
                    f"falling back to Gemini: {e}"
                )

        # Default: call Gemini
        generation_config = {"temperature": temperature}
        if json_mode:
            generation_config["response_mime_type"] = "application/json"

        model = genai.GenerativeModel(
            model_name,
            generation_config=generation_config,
        )
        response = model.generate_content(prompt)

        # Extract real token counts from usage_metadata (not word-splitting)
        usage = {"prompt_tokens": 0, "completion_tokens": 0}
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            meta = response.usage_metadata
            usage["prompt_tokens"] = getattr(meta, "prompt_token_count", 0) or 0
            usage["completion_tokens"] = getattr(meta, "candidates_token_count", 0) or 0
        else:
            # Fallback estimate (1.3 tokens per word) — better than 1:1
            usage["prompt_tokens"] = int(len(prompt.split()) * 1.3)
            usage["completion_tokens"] = int(len((response.text or "").split()) * 1.3)

        self.gemini_input_tokens += usage["prompt_tokens"]
        self.gemini_output_tokens += usage["completion_tokens"]

        return (response.text or "").strip(), usage

    # ========================================================================
    # TOGETHER AI — call a fine-tuned model hosted on Together
    # ========================================================================

    async def _call_together_model(
        self,
        model_id: str,
        prompt: str,
        temperature: float,
        json_mode: bool,
        _max_retries: int = 3,
    ) -> tuple[str, dict]:
        """Call a fine-tuned LoRA model on Together AI's inference API.

        Includes exponential backoff for transient failures (429, 500, 502, 503, 504).
        """

        import os
        import aiohttp

        api_key = os.getenv("TOGETHER_API_KEY", "")
        if not api_key:
            raise RuntimeError("TOGETHER_API_KEY not set — cannot call fine-tuned model")

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload: dict = {
            "model": model_id,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": 2048,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        last_error = None
        for attempt in range(_max_retries):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        "https://api.together.xyz/v1/chat/completions",
                        headers=headers,
                        json=payload,
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            text = data["choices"][0]["message"]["content"]
                            remote_usage = data.get("usage", {})
                            usage = {
                                "prompt_tokens": remote_usage.get("prompt_tokens", 0),
                                "completion_tokens": remote_usage.get("completion_tokens", 0),
                            }
                            self.gemini_input_tokens += usage["prompt_tokens"]
                            self.gemini_output_tokens += usage["completion_tokens"]
                            return text.strip(), usage

                        # Retryable status codes
                        if resp.status in (429, 500, 502, 503, 504):
                            body = await resp.text()
                            last_error = RuntimeError(
                                f"Together AI ({resp.status}): {body[:200]}"
                            )
                            backoff = 2 ** attempt  # 1s, 2s, 4s
                            logger.warning(
                                f"[{self.agent_type.upper()}] Together AI {resp.status}, "
                                f"retrying in {backoff}s (attempt {attempt + 1}/{_max_retries})"
                            )
                            await asyncio.sleep(backoff)
                            continue

                        # Non-retryable error
                        error = await resp.text()
                        raise RuntimeError(f"Together AI error ({resp.status}): {error}")

            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_error = e
                backoff = 2 ** attempt
                logger.warning(
                    f"[{self.agent_type.upper()}] Together AI network error: {e}, "
                    f"retrying in {backoff}s (attempt {attempt + 1}/{_max_retries})"
                )
                await asyncio.sleep(backoff)

        # All retries exhausted
        raise RuntimeError(
            f"Together AI failed after {_max_retries} attempts: {last_error}"
        )

    def parse_json_response(self, text: str) -> Any:
        """
        Robust JSON extraction from Gemini output.
        Strips markdown code blocks and handles common malformations.
        """
        text = text.strip()
        # Strip markdown code fences
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```\s*$", "", text)

        # Try direct parse first
        try:
            return json_module.loads(text)
        except json_module.JSONDecodeError:
            pass

        # Try extracting JSON object or array
        for pattern in [r"\{.*\}", r"\[.*\]"]:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                try:
                    return json_module.loads(match.group())
                except json_module.JSONDecodeError:
                    continue

        logger.warning(f"[{self.agent_type}] Failed to parse JSON from Gemini response")
        return None

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

            text, usage = await self.call_gemini(
                prompt,
                temperature=self.TEMPERATURE_SCORING,
                json_mode=True,
            )

            # Parse tool calls
            tool_calls = self._parse_tool_calls_json(text)
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

            text, usage = await self.call_gemini(
                prompt,
                temperature=self.TEMPERATURE_CREATIVE,
                json_mode=True,
            )

            synthesis = self.parse_json_response(text) or {
                "response": text,
                "action_items": [],
                "confidence": 50,
                "follow_up": "Let me help you further.",
            }
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

            # Calculate elapsed time and cost (using real token counts from usage_metadata)
            self.end_time = time.time()
            execution_time = self.end_time - self.start_time

            # Gemini 1.5 Flash pricing (April 2026): $0.075/1M input, $0.30/1M output
            input_cost = (self.gemini_input_tokens / 1_000_000) * 0.075
            output_cost = (self.gemini_output_tokens / 1_000_000) * 0.30
            total_cost_cents = max(1, int((input_cost + output_cost) * 100))  # Minimum 1 cent

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

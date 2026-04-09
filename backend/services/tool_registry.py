"""
Tool Registry - Dynamic tool registration and validation

Allows agents to discover and call tools without hard-coding them.
"""

import logging
import inspect
from typing import Dict, Callable, Any, Optional

logger = logging.getLogger(__name__)


class ToolRegistry:
    """
    Registry for agent tools.
    
    Usage:
        registry = ToolRegistry()
        registry.register("strength_analyzer", strength_analyzer_func)
        tools = registry.get_all()  # {'strength_analyzer': func, ...}
    """

    def __init__(self):
        self._tools: Dict[str, Dict[str, Any]] = {}

    def register(
        self,
        name: str,
        func: Callable,
        description: str = None,
        category: str = "general",
    ) -> None:
        """
        Register a tool (function) in the registry.
        
        Args:
            name: Tool identifier (e.g., "strength_analyzer")
            func: Async callable
            description: Natural language description
            category: Tool category (e.g., "analysis", "generation")
        """
        if name in self._tools:
            logger.warning(f"[REGISTRY] Tool '{name}' already registered. Overwriting.")

        # Extract function signature
        sig = inspect.signature(func)
        params = {
            param_name: {
                "type": param.annotation.__name__ if param.annotation != inspect.Parameter.empty else "unknown",
                "default": param.default if param.default != inspect.Parameter.empty else None,
            }
            for param_name, param in sig.parameters.items()
        }

        self._tools[name] = {
            "func": func,
            "description": description or func.__doc__ or "No description",
            "category": category,
            "params": params,
            "is_async": inspect.iscoroutinefunction(func),
        }

        logger.info(f"[REGISTRY] Registered tool: {name}")

    def get(self, name: str) -> Optional[Dict[str, Any]]:
        """Get a single tool by name"""
        return self._tools.get(name)

    def get_all(self) -> Dict[str, Callable]:
        """Get all registered tools as {name: func} dict"""
        return {name: info["func"] for name, info in self._tools.items()}

    def get_descriptions(self) -> str:
        """Get natural language descriptions of all tools (for LLM context)"""
        descriptions = []
        for name, info in self._tools.items():
            descriptions.append(f"- **{name}**: {info['description']}")
        return "\n".join(descriptions)

    def get_by_category(self, category: str) -> Dict[str, Callable]:
        """Get all tools in a specific category"""
        return {
            name: info["func"]
            for name, info in self._tools.items()
            if info["category"] == category
        }

    def validate_tool_call(self, tool_name: str, args: Dict[str, Any]) -> tuple:
        """
        Validate that a tool call is well-formed.
        
        Returns:
            (valid: bool, error_message: str)
        """
        if tool_name not in self._tools:
            return False, f"Tool '{tool_name}' not found"

        tool_info = self._tools[tool_name]
        required_params = []

        for param_name, param_info in tool_info["params"].items():
            if param_info["default"] is None and param_name not in args:
                required_params.append(param_name)

        if required_params:
            return (
                False,
                f"Missing required parameters: {', '.join(required_params)}",
            )

        return True, ""

    def list_tools(self) -> Dict[str, str]:
        """List all registered tools with descriptions"""
        return {
            name: info["description"] for name, info in self._tools.items()
        }


# Global registry (can be imported by agents)
global_tool_registry = ToolRegistry()

"""Exponential backoff retry logic for Gemini API calls and other external services."""

import asyncio
import logging
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


async def with_exponential_backoff(
    func: Callable[..., Any],
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    *args,
    **kwargs
) -> Any:
    """
    Execute an async function with exponential backoff retry logic.

    Args:
        func: Async function to retry
        max_retries: Maximum number of retry attempts (default: 3)
        base_delay: Initial delay in seconds (default: 1.0)
        max_delay: Maximum delay cap in seconds (default: 30.0)
        *args: Positional arguments to pass to func
        **kwargs: Keyword arguments to pass to func

    Returns:
        The result of func if successful

    Raises:
        The last exception if all retries are exhausted

    Example:
        result = await with_exponential_backoff(
            gemini_service.analyze_resume_match,
            max_retries=3,
            base_delay=1.0,
            resume_text=resume,
            job_description=jd
        )
    """
    last_exception = None
    delay = base_delay

    for attempt in range(max_retries + 1):
        try:
            result = await func(*args, **kwargs)
            if attempt > 0:
                logger.info(f"✓ Succeeded on retry {attempt}/{max_retries}")
            return result

        except asyncio.TimeoutError as e:
            last_exception = e
            if attempt < max_retries:
                logger.warning(
                    f"Timeout on attempt {attempt + 1}/{max_retries + 1}. "
                    f"Retrying in {delay}s..."
                )
                await asyncio.sleep(delay)
                delay = min(delay * 2, max_delay)  # Exponential backoff, capped
            else:
                logger.error(f"Timeout: all {max_retries + 1} attempts exhausted")

        except Exception as e:
            last_exception = e
            if attempt < max_retries:
                logger.warning(
                    f"Error on attempt {attempt + 1}/{max_retries + 1}: {str(e)}. "
                    f"Retrying in {delay}s..."
                )
                await asyncio.sleep(delay)
                delay = min(delay * 2, max_delay)
            else:
                logger.error(f"All {max_retries + 1} attempts exhausted: {str(e)}")

    # All retries exhausted
    raise last_exception if last_exception else Exception("All retries exhausted without error")


def exponential_backoff_decorator(max_retries: int = 3):
    """
    Decorator version of exponential backoff retry logic.

    Example:
        @exponential_backoff_decorator(max_retries=3)
        async def my_function():
            ...
    """
    def decorator(func: Callable) -> Callable:
        async def wrapper(*args, **kwargs):
            return await with_exponential_backoff(
                func,
                max_retries=max_retries,
                *args,
                **kwargs
            )
        return wrapper
    return decorator

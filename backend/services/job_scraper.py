"""
Job Description Scraper - Extract text from job posting URLs

Uses trafilatura (lightweight, no headless browser).
"""

import logging
import asyncio
from typing import Optional

import trafilatura

logger = logging.getLogger(__name__)


async def scrape_job_description(url: str) -> str:
    """
    Fetch and extract clean text from a job posting URL.
    
    Args:
        url: Full URL to job posting (LinkedIn, Indeed, etc.)
    
    Returns:
        Extracted job description text (max 5000 chars)
    
    Raises:
        ValueError: If extraction fails or returns empty
    """
    try:
        # Run blocking trafilatura in thread to avoid blocking async loop
        downloaded = await asyncio.to_thread(trafilatura.fetch_url, url)
        if not downloaded:
            raise ValueError("Could not fetch URL content")

        # Extract main content
        content = await asyncio.to_thread(
            trafilatura.extract,
            downloaded,
            include_comments=False,
            include_tables=False,
            no_fallback=False,
        )

        if not content or len(content.strip()) < 100:
            raise ValueError("Extracted content is too short or empty")

        # Trim to reasonable length for LLM context
        max_chars = 5000
        if len(content) > max_chars:
            content = content[:max_chars] + "..."

        logger.info(f"[SCRAPER] Successfully extracted {len(content)} chars from {url}")
        return content.strip()

    except Exception as e:
        logger.error(f"[SCRAPER] Failed to scrape {url}: {e}")
        raise ValueError(f"Job description extraction failed: {e}")

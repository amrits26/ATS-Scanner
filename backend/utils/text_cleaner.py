"""Text cleaning and normalization utilities for resume and JD extraction."""

import re
from typing import Optional


def clean_extracted_text(raw: str) -> str:
    """
    Clean and normalize extracted text from PDF/DOCX.
    Handles extra whitespace, control chars, and common extraction artifacts.
    """
    if not raw or not isinstance(raw, str):
        return ""
    # Replace control chars and weird unicode
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", " ", raw)
    # Normalize line breaks
    text = re.sub(r"\r\n|\r", "\n", text)
    # Collapse multiple spaces/newlines
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.strip()
    return text


def normalize_for_ats(text: str) -> str:
    """Normalize text for ATS comparison (lowercase, single spaces)."""
    if not text:
        return ""
    text = clean_extracted_text(text)
    text = re.sub(r"\s+", " ", text).strip().lower()
    return text


def extract_words(text: str) -> list[str]:
    """Extract alphanumeric tokens (words) for keyword analysis."""
    if not text:
        return []
    cleaned = normalize_for_ats(text)
    return re.findall(r"[a-z0-9]+", cleaned)

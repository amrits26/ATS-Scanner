"""Bonus: weak verb detection, metric detection, passive voice, readability, section detection."""

import os
import re
from typing import Any

from openai import AsyncOpenAI

from ..models import WritingFeedback
from ..utils.text_cleaner import clean_extracted_text

# Common weak verbs to flag
WEAK_VERBS = {
    "helped", "help", "helps", "worked", "work", "works", "did", "do", "does",
    "made", "make", "makes", "got", "get", "gets", "used", "use", "uses",
    "responsible", "involved", "participated", "assisted", "assist",
}

# Passive indicators (simplified)
PASSIVE_PATTERN = re.compile(
    r"\b(was|were|been|being|is|are)\s+(\w+ed|\w+en)\b",
    re.I,
)


def _extract_bullets(text: str) -> list[str]:
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    bullets = []
    for ln in lines:
        for prefix in ("•", "-", "*", "◦"):
            if ln.startswith(prefix):
                bullets.append(ln[len(prefix):].strip())
                break
        else:
            if bullets and not ln.startswith(("SUMMARY", "EXPERIENCE", "EDUCATION", "SKILLS")):
                bullets.append(ln)
    return bullets


def detect_weak_verbs(text: str) -> list[str]:
    """Return phrases/bullets that contain weak verbs."""
    found: list[str] = []
    lower = text.lower()
    words = set(re.findall(r"\b[a-z]+\b", lower))
    weak_used = words & WEAK_VERBS
    for bullet in _extract_bullets(text):
        bl = bullet.lower()
        for w in weak_used:
            if w in bl and bullet not in found:
                found.append(bullet[:80])
                break
    return found[:15]


def detect_bullets_without_metrics(text: str) -> list[str]:
    """Bullets that don't contain numbers (potential lack of impact)."""
    number = re.compile(r"\d+")
    without: list[str] = []
    for bullet in _extract_bullets(text):
        if not number.search(bullet) and len(bullet) > 20:
            without.append(bullet[:80])
    return without[:15]


def detect_passive_voice(text: str) -> list[str]:
    """Simple passive voice phrase detection."""
    found: list[str] = []
    for m in PASSIVE_PATTERN.finditer(text):
        start = max(0, m.start() - 20)
        end = min(len(text), m.end() + 30)
        snippet = text[start:end].strip()
        if snippet not in found:
            found.append(snippet)
    return found[:10]


def detect_sections(text: str) -> list[str]:
    """Detect section headers (SUMMARY, EXPERIENCE, etc.)."""
    sections = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        if line.isupper() and len(line) < 50:
            sections.append(line)
        elif line.lower() in ("summary", "experience", "education", "skills", "projects", "certifications"):
            sections.append(line)
    return sections if sections else ["(sections not detected)"]


def readability_simple(text: str) -> float:
    """Simple readability: avg word length and sentence length heuristic. 0–1 scale."""
    if not text:
        return 0.0
    sentences = [s.strip() for s in re.split(r"[.!?]+", text) if s.strip()]
    if not sentences:
        return 0.5
    words = re.findall(r"\b\w+\b", text)
    if not words:
        return 0.5
    avg_word_len = sum(len(w) for w in words) / len(words) if words else 0
    avg_sent_len = len(words) / len(sentences) if sentences else 0
    # Heuristic: ideal word length ~5, ideal sentence length ~15 words
    word_score = 1.0 - abs(avg_word_len - 5) / 10.0
    sent_score = 1.0 - abs(avg_sent_len - 15) / 20.0
    return max(0.0, min(1.0, (word_score + sent_score) / 2.0))


async def get_writing_feedback(optimized_resume: str) -> WritingFeedback:
    """Get comprehensive writing feedback on the optimized resume."""
    if not optimized_resume or len(optimized_resume.strip()) < 10:
        return WritingFeedback()
    
    cleaned = clean_extracted_text(optimized_resume)
    return WritingFeedback(
        weak_verbs_detected=detect_weak_verbs(cleaned),
        bullets_without_metrics=detect_bullets_without_metrics(cleaned),
        passive_voice_phrases=detect_passive_voice(cleaned),
        readability_score=readability_simple(cleaned),
        sections_detected=detect_sections(cleaned),
    )
    avg_word = sum(len(w) for w in words) / len(words)
    avg_sent = len(words) / len(sentences)
    # Rough scale: good resume ~15–25 words/sentence, word len ~4–5
    score = 1.0 - min(1.0, (avg_sent - 15) / 30) * 0.5 - min(1.0, abs(avg_word - 5) / 5) * 0.3
    return round(max(0, min(1, score)), 2)


async def get_writing_feedback(resume_text: str) -> WritingFeedback:
    """Aggregate writing feedback (weak verbs, metrics, passive, readability, sections)."""
    cleaned = clean_extracted_text(resume_text)
    return WritingFeedback(
        weak_verbs_detected=detect_weak_verbs(cleaned),
        bullets_without_metrics=detect_bullets_without_metrics(cleaned),
        passive_voice_phrases=detect_passive_voice(cleaned),
        readability_score=readability_simple(cleaned),
        sections_detected=detect_sections(cleaned),
    )

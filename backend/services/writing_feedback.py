"""Bonus: weak verb detection, metric detection, passive voice, readability, section detection."""

import re
from typing import Any

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


def _generate_default_suggestions(text: str) -> list[str]:
    """Generate default improvement suggestions if all detection lists are empty."""
    suggestions = []
    
    # Check for specific patterns
    if "I " in text:
        suggestions.append("Use strong action verbs (e.g., 'Spearheaded', 'Architected') instead of 'I' statements")
    
    if "responsible for" in text.lower():
        suggestions.append("Replace 'responsible for' with specific action verbs (e.g., 'Managed', 'Led')")
    
    if "worked on" in text.lower():
        suggestions.append("Replace vague terms like 'worked on' with specific accomplishments and metrics")
    
    if "team" in text.lower() and not any(c.isdigit() for c in text.split("team")[0][-10:]):
        suggestions.append("Quantify team size: instead of 'Led team', specify 'Led team of X professionals'")
    
    # Default suggestions if none of the above
    if not suggestions:
        suggestions = [
            "Add quantifiable metrics to demonstrate impact (e.g., '30% improvement', '$2M revenue')",
            "Replace weak verbs with strong action verbs: Led, Engineered, Architected, Optimized, Spearheaded",
            "Ensure each bullet point starts with an action verb and includes a business outcome",
        ]
    
    return suggestions


async def get_writing_feedback(optimized_resume: str) -> WritingFeedback:
    """Get comprehensive writing feedback on the optimized resume. Ensures suggestions never empty."""
    if not optimized_resume or len(optimized_resume.strip()) < 10:
        return WritingFeedback(
            weak_verbs_detected=_generate_default_suggestions(optimized_resume),
        )
    
    cleaned = clean_extracted_text(optimized_resume)
    
    weak_verbs = detect_weak_verbs(cleaned)
    bullets_no_metrics = detect_bullets_without_metrics(cleaned)
    passive_voice = detect_passive_voice(cleaned)
    
    # Ensure we always have suggestions (combine all findings)
    suggestions = weak_verbs + bullets_no_metrics + passive_voice
    
    # If no suggestions found, generate defaults
    if not suggestions:
        suggestions = _generate_default_suggestions(cleaned)
    
    # Use weak_verbs field to store all suggestions
    return WritingFeedback(
        weak_verbs_detected=suggestions,
        bullets_without_metrics=bullets_no_metrics,
        passive_voice_phrases=passive_voice,
        readability_score=readability_simple(cleaned),
        sections_detected=detect_sections(cleaned),
    )

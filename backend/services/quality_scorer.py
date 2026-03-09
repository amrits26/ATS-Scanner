"""Resume quality scoring based on multiple factors."""

import re
from ..models import ResumeQualityScore
from ..utils.text_cleaner import extract_words, normalize_for_ats


def calculate_readability_score(text: str) -> float:
    """Calculate readability score 0-100."""
    if not text or len(text) < 10:
        return 0.0
    
    sentences = [s.strip() for s in re.split(r"[.!?]+", text) if s.strip()]
    words = re.findall(r"\b\w+\b", text)
    
    if not words or not sentences:
        return 50.0
    
    avg_word_len = sum(len(w) for w in words) / len(words)
    avg_sent_len = len(words) / len(sentences)
    
    # Ideal: word length ~5, sentence length ~15 words
    word_score = max(0, 100 - abs(avg_word_len - 5) * 10)
    sent_score = max(0, 100 - abs(avg_sent_len - 15) * 2)
    
    return round((word_score + sent_score) / 2, 1)


def calculate_formatting_score(text: str) -> float:
    """Score based on formatting structure and clarity."""
    score = 50.0  # Base
    
    # Check for section headers
    sections_found = len(re.findall(r"\b(SUMMARY|EXPERIENCE|EDUCATION|SKILLS|PROJECTS)\b", text, re.I))
    if sections_found >= 3:
        score += 20
    elif sections_found >= 2:
        score += 15
    
    # Check for bullet points
    bullet_count = len(re.findall(r"^\s*[-•*]\s+", text, re.M))
    if bullet_count >= 5:
        score += 15
    elif bullet_count >= 2:
        score += 10
    
    # Check for consistent capitalization
    caps_lines = len(re.findall(r"^\s*[A-Z][A-Z\s]+$", text, re.M))
    if caps_lines >= 2:
        score += 10
    
    # Check for excessive whitespace issues (negative)
    if re.search(r"\n{4,}", text):
        score -= 10
    
    return min(100.0, max(0.0, score))


def calculate_content_score(text: str, jd_text: str = "") -> float:
    """Score based on content richness and relevance."""
    score = 40.0
    
    # Check for action verbs
    action_verbs = {
        "led", "managed", "developed", "created", "designed", "implemented",
        "improved", "optimized", "increased", "reduced", "achieved", "launched",
        "built", "established", "coordinated", "directed", "executed"
    }
    text_lower = text.lower()
    action_verb_count = sum(1 for verb in action_verbs if verb in text_lower)
    
    if action_verb_count >= 10:
        score += 30
    elif action_verb_count >= 5:
        score += 20
    elif action_verb_count >= 2:
        score += 10
    
    # Check for quantifiable metrics
    metric_count = len(re.findall(r"\d+[\s%$K-M]+|[\d.]+x|#\d+", text))
    if metric_count >= 10:
        score += 15
    elif metric_count >= 5:
        score += 10
    
    # Check for experience breadth (multiple technologies/tools mentioned)
    tech_keywords = {"python", "javascript", "java", "sql", "aws", "azure", "api", "rest", "react", "angular",
                     "node", "django", "flask", "spring", "kubernetes", "docker", "git", "ci/cd"}
    tech_found = sum(1 for tech in tech_keywords if tech in text_lower)
    if tech_found >= 5:
        score += 10
    
    return min(100.0, max(0.0, score))


def calculate_keyword_density_score(text: str, jd_text: str = "") -> float:
    """Score based on keyword density and variety."""
    if not text or not jd_text:
        return 50.0
    
    text_words = extract_words(text)
    jd_words = extract_words(jd_text)
    
    if not text_words or not jd_words:
        return 50.0
    
    # Check overlap
    text_set = set(text_words)
    jd_set = set(jd_words)
    overlap = len(text_set & jd_set)
    overlap_pct = (overlap / len(jd_set)) * 100 if jd_set else 0
    
    # Keywords should be 20-40% overlap (not too low, not too spammy)
    if 20 <= overlap_pct <= 40:
        score = 100.0
    elif 15 <= overlap_pct <= 50:
        score = 80.0
    elif 10 <= overlap_pct <= 60:
        score = 60.0
    else:
        score = min(overlap_pct, 50.0)
    
    return round(score, 1)


def generate_quality_feedback(text: str, scores: dict) -> list[str]:
    """Generate actionable feedback based on quality scores."""
    feedback = []
    
    if scores["readability"] < 60:
        feedback.append("✓ Improve sentence clarity - use shorter, punchier sentences")
    
    if scores["formatting"] < 60:
        feedback.append("✓ Add clear section headings (EXPERIENCE, SKILLS, EDUCATION)")
        feedback.append("✓ Use bullet points for better readability")
    
    if scores["content"] < 60:
        feedback.append("✓ Add more action verbs (led, managed, developed, etc.)")
        feedback.append("✓ Include measurable achievements with numbers/percentages")
    
    if scores["keyword_density"] < 50:
        feedback.append("✓ Add more relevant keywords from the job description")
    
    # Positive feedback
    if scores["readability"] >= 70:
        feedback.append("✓ Good readability - sentences are well-structured")
    if scores["formatting"] >= 70:
        feedback.append("✓ Excellent formatting with clear sections")
    if scores["content"] >= 70:
        feedback.append("✓ Strong action verbs and quantifiable achievements")
    
    return feedback if feedback else ["✓ Overall good quality resume!"]


def calculate_resume_quality(text: str, jd_text: str = "") -> ResumeQualityScore:
    """Calculate comprehensive resume quality score."""
    readability = calculate_readability_score(text)
    formatting = calculate_formatting_score(text)
    content = calculate_content_score(text, jd_text)
    keyword_density = calculate_keyword_density_score(text, jd_text)
    
    scores = {
        "readability": readability,
        "formatting": formatting,
        "content": content,
        "keyword_density": keyword_density,
    }
    
    # Weighted overall score
    overall = round(
        readability * 0.25 + formatting * 0.25 + content * 0.35 + keyword_density * 0.15,
        1
    )
    
    feedback = generate_quality_feedback(text, scores)
    
    return ResumeQualityScore(
        overall_score=min(100.0, max(0.0, overall)),
        readability_score=readability,
        formatting_score=formatting,
        content_score=content,
        keyword_density_score=keyword_density,
        feedback=feedback,
    )

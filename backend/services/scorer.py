"""ATS match scoring: keyword overlap, TF-IDF cosine similarity, weighted final score."""

from typing import Optional

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from ..models import ATSScoreResponse, JobDescriptionAnalysis
from ..utils.text_cleaner import normalize_for_ats, extract_words


def compute_ats_score(
    resume_text: str,
    jd_text: str,
    jd_analysis: Optional[JobDescriptionAnalysis] = None,
) -> ATSScoreResponse:
    """
    Compute keyword match %, semantic (TF-IDF) similarity, and weighted final score.
    Derives missing and recommended keywords from JD analysis or full JD text.
    """
    r_norm = normalize_for_ats(resume_text or "")
    j_norm = normalize_for_ats(jd_text or "")
    if not r_norm and not j_norm:
        return ATSScoreResponse()

    # Collect JD keywords: from structured analysis or from full JD text
    jd_keywords: list[str] = []
    if jd_analysis:
        jd_keywords = (
            jd_analysis.keywords
            + jd_analysis.required_skills
            + jd_analysis.preferred_skills
            + jd_analysis.tools
        )
    if not jd_keywords:
        jd_keywords = list(dict.fromkeys(extract_words(jd_text)))  # dedupe

    resume_words = set(extract_words(resume_text))
    # Flatten and dedupe JD keywords into individual tokens
    all_jd_tokens = set()
    for k in jd_keywords:
        if k:
            all_jd_tokens.update(normalize_for_ats(k).split())
    # Also add original phrases as single normalized tokens where meaningful
    for k in jd_keywords:
        if k:
            token = normalize_for_ats(k).replace(" ", "")
            if len(token) > 1:
                all_jd_tokens.add(token)
    for w in extract_words(jd_text):
        if len(w) > 2:
            all_jd_tokens.add(w)

    # Keyword match: how many JD keywords appear in resume
    if all_jd_tokens:
        matched = resume_words & all_jd_tokens
        keyword_match_percent = round(100.0 * len(matched) / len(all_jd_tokens), 1)
        missing = sorted(all_jd_tokens - resume_words)
        # Limit missing list size; recommend top by importance (e.g. from required_skills first)
        recommended = missing[:30]
        if jd_analysis and jd_analysis.required_skills:
            req_tokens = set()
            for s in jd_analysis.required_skills:
                req_tokens.update(extract_words(s))
            missing_req = sorted(req_tokens - resume_words)[:15]
            recommended = list(dict.fromkeys(missing_req + [k for k in missing if k not in missing_req]))[:30]
    else:
        keyword_match_percent = 0.0
        missing = []
        recommended = []

    # TF-IDF cosine similarity
    semantic_similarity_score = 0.0
    if r_norm and j_norm:
        try:
            vectorizer = TfidfVectorizer(max_features=5000, ngram_range=(1, 2), stop_words="english")
            matrix = vectorizer.fit_transform([r_norm, j_norm])
            sim = cosine_similarity(matrix[0:1], matrix[1:2])
            semantic_similarity_score = round(float(sim[0, 0]), 4)
        except Exception:
            semantic_similarity_score = 0.0

    # Weighted final score (0–100): blend keyword and semantic
    weight_keyword = 0.55
    weight_semantic = 0.45
    final_ats_score = round(
        (keyword_match_percent / 100.0) * weight_keyword + semantic_similarity_score * weight_semantic,
        1,
    )
    final_ats_score = min(100.0, max(0.0, final_ats_score * 100.0))

    return ATSScoreResponse(
        keyword_match_percent=keyword_match_percent,
        semantic_similarity_score=semantic_similarity_score,
        final_ats_score=final_ats_score,
        missing_keywords=missing[:50],
        recommended_keywords_to_add=recommended[:30],
    )

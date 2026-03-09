"""Generate keyword heatmap data for visualization."""

from collections import Counter
from ..models import KeywordHeatmapData
from ..utils.text_cleaner import extract_words, normalize_for_ats


def _get_stopwords_set() -> set[str]:
    """Load stopwords from NLTK if available, otherwise use built-in list."""
    try:
        from nltk.corpus import stopwords
        return set(stopwords.words("english"))
    except (ImportError, LookupError):
        # Fallback to comprehensive built-in stopwords list (common English words)
        return {
            # Articles and prepositions
            "the", "a", "an", "and", "or", "is", "are", "was", "were", "be", "been",
            "have", "has", "had", "do", "does", "did", "will", "would", "should", "could",
            "may", "might", "must", "can", "for", "of", "in", "on", "at", "to", "by",
            "as", "with", "from", "up", "about", "into", "through", "out", "that",
            "this", "which", "who", "what", "where", "when", "why", "how",
            # Common verbs and auxiliary verbs
            "get", "got", "make", "made", "come", "came", "see", "saw", "go", "went",
            "know", "knew", "take", "took", "think", "thought", "use", "used",
            # Common adjectives
            "all", "any", "each", "every", "both", "few", "more", "most", "other",
            "some", "such", "no", "nor", "not", "own", "same", "so", "than", "too",
            "very", "just", "only", "also", "while", "again", "over", "well", "good",
            "able", "new", "old", "right", "real", "best", "first", "last", "long",
            # Common nouns and pronouns  
            "he", "she", "it", "we", "they", "you", "i", "me", "him", "her", "us",
            "them", "my", "your", "his", "her", "its", "our", "their",
            # Common adverbs
            "here", "there", "now", "then", "before", "after", "above", "below",
            "further", "further", "together", "even", "else", "back", "still", "down",
            # Conjunctions and common words
            "because", "since", "if", "unless", "until", "while", "whereas", "though",
        }


def generate_keyword_heatmap(
    resume_text: str,
    jd_text: str,
    top_n: int = 20,
) -> KeywordHeatmapData:
    """
    Generate keyword frequency heatmap data.
    Shows how often JD keywords (hard/soft skills) appear in resume.
    Filters out common English stopwords to focus on meaningful skills.
    """
    jd_norm = normalize_for_ats(jd_text or "")
    resume_norm = normalize_for_ats(resume_text or "")
    
    # Extract words and count
    jd_words = extract_words(jd_norm)
    resume_words = extract_words(resume_norm)
    
    # Count frequencies in JD
    jd_counter = Counter(jd_words)
    resume_counter = Counter(resume_words)
    
    # Get top JD keywords
    top_jd_keywords = jd_counter.most_common(top_n * 3)  # Get more, filter below
    
    # Load stopwords
    stopwords = _get_stopwords_set()
    
    keywords = []
    frequencies = []
    importance_scores = []
    
    for keyword, jd_freq in top_jd_keywords:
        # Skip if too short (less than 3 chars) or in stopwords
        if len(keyword) < 3 or keyword in stopwords:
            continue
        
        resume_freq = resume_counter.get(keyword, 0)
        keywords.append(keyword)
        frequencies.append(resume_freq)
        
        # Importance score: how important is this in JD vs how much in resume
        # Normalized frequency in JD
        jd_norm_freq = jd_freq / max(1, len(jd_words))
        # Score: 0-1, but also consider if it appears in resume
        importance = min(1.0, jd_norm_freq * 10)  # Scale up for visibility
        if resume_freq > 0:
            importance *= (1 + 0.2)  # Boost if in resume (matched skill)
        
        importance_scores.append(min(1.0, importance))
        
        if len(keywords) >= top_n:
            break
    
    return KeywordHeatmapData(
        keywords=keywords,
        frequencies=frequencies,
        importance_scores=importance_scores,
    )

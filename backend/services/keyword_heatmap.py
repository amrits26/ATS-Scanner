"""Generate keyword heatmap data for visualization."""

from collections import Counter
from ..models import KeywordHeatmapData
from ..utils.text_cleaner import extract_words, normalize_for_ats
from .agent_base import TECH_ACRONYM_WHITELIST


def _get_stopwords_set() -> set[str]:
    """Load stopwords from NLTK if available, otherwise use comprehensive built-in list."""
    try:
        from nltk.corpus import stopwords
        return set(stopwords.words("english"))
    except (ImportError, LookupError):
        # Comprehensive stopwords list - filters junk keywords like 401, ability, actionable, etc
        stopwords_set = {
            "the", "a", "an", "and", "or", "is", "are", "was", "were", "be", "been",
            "have", "has", "had", "do", "does", "did", "will", "would", "should", "could",
            "may", "might", "must", "can", "for", "of", "in", "on", "at", "to", "by",
            "as", "with", "from", "up", "about", "into", "through", "out", "that",
            "this", "which", "who", "what", "where", "when", "why", "how",
            "get", "got", "make", "made", "come", "came", "see", "saw", "go", "went",
            "know", "knew", "take", "took", "think", "thought", "use", "used",
            "include", "provide", "develop", "create", "build", "work", "help", "lead", "manage",
            "all", "any", "each", "every", "both", "few", "more", "most", "other",
            "some", "such", "no", "nor", "not", "own", "same", "so", "than", "too",
            "very", "just", "only", "also", "while", "again", "over", "well", "good",
            "new", "old", "right", "real", "best", "first", "last", "long", "able",
            "he", "she", "it", "we", "they", "you", "i", "me", "him", "her", "us",
            "them", "my", "your", "his", "her", "its", "our", "their",
            "here", "there", "now", "then", "before", "after", "above", "below",
            "further", "together", "even", "else", "back", "still", "down",
            "because", "since", "if", "unless", "until", "whereas", "though",
            "ability", "acumen", "action", "actionable", "activities", "activity",
            "adoption", "agencies", "agency", "aligned", "alignment", "amount",
            "analytic", "analytical", "analyze", "analyzed", "analyzing",
            "applicable", "applicant", "applied", "applying", "appreciate",
            "appreciation", "appropriate", "approval", "approvals", "approve",
            "approved", "areas", "argued", "argument", "arise", "arose",
            "associated", "associates", "association", "assurance", "attention",
            "attitude", "authentic", "authorities", "authorization", "availability",
            "avenue", "aware", "awareness", "benefit", "benefits", "bereavement",
            "better", "body", "bonus", "both", "candidate", "certification",
            "collaborate", "communication", "company", "compensation",
            "competitive", "comprehensive", "conduct", "conducted",
            "confidential", "consistent", "continuous", "contribute",
            "contribution", "control", "coordinated", "coordination",
            "core", "corporate", "correct", "cost", "create", "created",
            "critical", "culture", "current", "customer", "data", "deliver",
            "delivered", "department", "depend", "dependent", "develop",
            "developed", "direct", "directly", "document", "documentation",
            "drive", "driven", "driving", "due", "during", "effective",
            "effectively", "efficiency", "efficient", "effort", "either",
            "employee", "employer", "employment", "enable", "enabled",
            "encourage", "enhance", "enhanced", "ensure", "environment",
            "equipment", "especially", "essential", "establish", "established",
            "evaluate", "evaluated", "event", "every", "everyone", "everything",
            "evidence", "exactly", "example", "excellent", "except", "excess",
            "excessive", "exchange", "exciting", "exclude", "excluding",
            "executive", "exercise", "exist", "existence", "existing", "expand",
            "expansion", "expect", "expected", "expensive", "experience",
            "experienced", "experiment", "expert", "explain", "explanation",
            "explicit", "explicitly", "explore", "exposure", "express",
            "expressed", "expression", "extend", "extended", "external",
            "extra", "extract", "extremely", "face", "facilitate", "facility",
            "fact", "factor", "fair", "fairly", "faith", "fall", "familiar",
            "family", "famous", "far", "fast", "fault", "favor", "favorite",
            "feature", "federal", "fee", "feed", "feedback", "feel", "feeling",
            "female", "few", "field", "fight", "figure", "file", "fill", "film",
            "final", "finally", "financial", "find", "fine", "finish", "fire",
            "firm", "first", "fit", "five", "fix", "focus", "follow", "following",
            "forget", "form", "formal", "format", "former", "forward", "found",
            "four", "free", "friend", "from", "front", "full", "fully", "fun",
            "function", "fund", "future", "gain", "game", "gap", "gather", "general",
            "generally", "generate", "generous", "get", "give", "given", "glass",
            "goal", "going", "good", "government", "grade", "grant", "great",
            "green", "ground", "group", "grow", "growth", "guard", "guess", "guide",
            "guy", "hair", "half", "hand", "handle", "hang", "happen", "happy",
            "hard", "hardly", "harm", "hate", "have", "head", "health", "hear",
            "heard", "heart", "heat", "heavy", "hell", "help", "hence", "her",
            "here", "hereafter", "hereby", "herein", "hereupon", "hers", "herself",
            "hesitate", "hi", "hide", "high", "highly", "him", "himself", "his",
            "history", "hit", "hold", "home", "hope", "horse", "host", "hot",
            "hotel", "hour", "house", "how", "however", "huge", "human", "hundred",
            "hung", "hungry", "hurt", "husband", "idea", "identify", "ignore",
            "image", "imagine", "impact", "important", "improve", "include",
            "including", "increase", "indeed", "indicate", "individual", "industry",
            "influence", "information", "inside", "insight", "instead", "interest",
            "internal", "international", "internet", "interview", "into", "introduce",
            "invest", "investigate", "involve", "involved", "issue", "it", "item",
            "its", "itself", "job", "join", "just", "keep", "key", "kill", "kind",
            "know", "knowledge", "lack", "land", "large", "last", "late", "laugh",
            "launch", "law", "lay", "lead", "learn", "least", "leave", "left",
            "legal", "less", "let", "level", "lie", "life", "light", "like",
            "likely", "line", "list", "little", "live", "load", "local", "lock",
            "log", "long", "look", "lord", "lose", "loss", "lot", "love", "low",
            "luck", "make", "man", "manage", "many", "market", "marketing",
            "master", "match", "material", "matter", "may", "maybe", "me", "mean",
            "measure", "meet", "member", "mention", "might", "million", "mind",
            "miss", "model", "modern", "moment", "money", "month", "more",
            "morning", "most", "mostly", "move", "much", "must", "my", "myself",
            "name", "national", "natural", "nature", "near", "necessary", "need",
            "network", "never", "new", "news", "next", "nice", "night", "no",
            "non", "none", "nor", "normal", "normally", "north", "northern",
            "not", "note", "nothing", "notice", "now", "number", "obvious",
            "occur", "offer", "office", "often", "oh", "ok", "old", "on", "once",
            "one", "only", "open", "operate", "opportunity", "option", "or",
            "order", "original", "other", "otherwise", "ought", "out", "outside",
            "over", "overall", "own", "pain", "paper", "parent", "part",
            "particular", "particularly", "party", "pass", "past", "pay", "people",
            "per", "percent", "perfect", "perhaps", "person", "personal", "phone",
            "pick", "picture", "piece", "place", "plan", "play", "point", "poor",
            "position", "positive", "possible", "post", "power", "practice",
            "prefer", "prepare", "present", "president", "press", "pressure",
            "pretty", "prevent", "price", "primary", "principle", "priority",
            "private", "probably", "problem", "process", "produce", "product",
            "professional", "program", "progress", "project", "property",
            "propose", "protect", "prove", "provide", "public", "pull", "purpose",
            "push", "put", "quality", "question", "quick", "quickly", "quiet",
            "quite", "raise", "range", "rate", "rather", "reach", "read", "ready",
            "real", "really", "reason", "receive", "recent", "recently", "recognize",
            "record", "red", "reduce", "reflect", "region", "relate", "relative",
            "relatively", "release", "relevant", "remain", "remember", "remove",
            "report", "represent", "require", "research", "resource", "respond",
            "response", "responsible", "rest", "result", "return", "reveal",
            "review", "right", "rise", "risk", "role", "room", "rule", "run",
            "safe", "same", "save", "say", "scale", "scene", "school", "science",
            "score", "sea", "search", "season", "seat", "second", "section",
            "security", "see", "seek", "seem", "select", "self", "sell", "send",
            "sense", "series", "serious", "serve", "service", "set", "settle",
            "seven", "several", "sex", "sexual", "shake", "shall", "shape",
            "share", "she", "shoot", "short", "shot", "should", "show", "side",
            "sight", "sign", "signal", "significant", "similar", "simple",
            "simply", "since", "sing", "single", "sir", "sit", "site", "situation",
            "size", "skill", "skin", "small", "smile", "so", "social", "society",
            "soft", "software", "soil", "soldier", "some", "somebody", "someone",
            "something", "sometimes", "somewhere", "son", "song", "soon", "sort",
            "sound", "source", "south", "southern", "space", "speak", "special",
            "specific", "speed", "spell", "spend", "staff", "stage", "stand",
            "standard", "start", "state", "station", "stay", "step", "still",
            "stop", "store", "story", "straight", "strange", "street", "strength",
            "stretch", "strike", "strong", "student", "study", "stuff", "style",
            "subject", "submit", "substantial", "succeed", "success", "such",
            "sudden", "suffer", "suggest", "summer", "sun", "supply", "support",
            "suppose", "sure", "surface", "surprise", "surround", "survey",
            "survive", "sweet", "swim", "system", "table", "take", "talk", "task",
            "team", "technical", "technology", "tell", "ten", "tend", "term",
            "test", "than", "thank", "that", "the", "their", "them", "themselves",
            "then", "there", "therefore", "these", "they", "thick", "thin",
            "thing", "think", "third", "this", "those", "though", "thought",
            "thousand", "three", "through", "throughout", "throw", "thus", "tie",
            "time", "tiny", "title", "to", "today", "together", "tomorrow",
            "tone", "too", "top", "total", "touch", "toward", "town", "track",
            "trade", "traffic", "train", "transport", "travel", "treat", "tree",
            "trial", "trip", "trouble", "true", "trust", "truth", "try", "turn",
            "twice", "two", "type", "under", "understand", "union", "unit",
            "unless", "until", "up", "upon", "use", "used", "useful", "user",
            "usual", "value", "various", "very", "view", "wait", "walk", "wall",
            "want", "war", "warm", "wash", "watch", "water", "way", "we", "wear",
            "week", "weight", "welcome", "well", "west", "western", "what",
            "whatever", "when", "where", "whereas", "whether", "which", "while",
            "white", "who", "whole", "whom", "why", "wide", "wife", "will",
            "win", "wish", "with", "within", "without", "woman", "wonder",
            "word", "work", "world", "worry", "would", "write", "wrong", "year",
            "yes", "yesterday", "yet", "you", "young", "your", "yours", "yourself",
            "http", "https", "json", "xml", "401", "403", "404", "500", "200",
            "database", "web", "mobile", "software", "system", "application",
            "0", "1", "2", "3", "4", "5", "6", "7", "8", "9",
        }
        print(f"[DEBUG] Stopwords loaded: {len(stopwords_set)} words")
        return stopwords_set


def _is_high_signal(word: str, stopwords: set[str]) -> bool:
    """
    Aggressive signal filter: only allow high-value skill/keyword tokens.
    Filters out junk, numbers, and low-signal words.
    Now uses shared TECH_ACRONYM_WHITELIST to preserve short but valid skills.
    """
    if not word:
        return False
    
    word_lower = word.lower()
    
    # Allow known tech acronyms regardless of length (AI, ML, QA, C#, Go, R)
    if word_lower in TECH_ACRONYM_WHITELIST:
        return True
    
    # Rule 1: Length check - must be > 2 characters
    if len(word) <= 2:
        return False
    
    # Rule 2: Reject pure numbers (catches "401", "2", "123", etc)
    if word.isdigit():
        return False
    
    # Rule 3: Reject stop words
    if word_lower in stopwords:
        return False
    
    # Rule 4: Reject if too many digits (>40%)
    digit_count = sum(1 for c in word if c.isdigit())
    if digit_count > 0 and digit_count / len(word) > 0.4:
        return False
    
    return True


def generate_keyword_heatmap(
    resume_text: str,
    jd_text: str,
    top_n: int = 20,
) -> KeywordHeatmapData:
    """
    Generate keyword frequency heatmap data with aggressive signal filtering.
    Shows how often JD keywords (hard/soft skills) appear in resume.
    Filters out common English stopwords and junk to focus on meaningful skills.
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
    filtered_out = []
    
    for keyword, jd_freq in top_jd_keywords:
        # Use aggressive signal filter - must pass ALL checks (not just length + stopwords)
        if not _is_high_signal(keyword, stopwords):
            filtered_out.append(keyword)
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
    
    # Debug logging
    print(f"[KEYWORD_HEATMAP] Generated {len(keywords)} keywords (filtered {len(filtered_out)})")
    print(f"[KEYWORD_HEATMAP] Clean keywords: {keywords[:10]}")
    if filtered_out:
        print(f"[KEYWORD_HEATMAP] Filtered out (junk): {filtered_out[:10]}")
    
    return KeywordHeatmapData(
        keywords=keywords,
        frequencies=frequencies,
        importance_scores=importance_scores,
    )

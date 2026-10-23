"""Sparse lexical ranking and a transparent, editable profile vector.

Deterministic, zero model tokens, offline. BM25-style is not needed at this
corpus size; TF-IDF cosine plus a Rocchio-style relevance-feedback profile is
enough and easy to explain.
"""
import math
import re
import unicodedata
from collections import OrderedDict
import sys
import threading

STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "we", "our", "is", "are",
    "that", "this", "as", "by", "from", "it", "its", "be", "can", "which", "these", "their", "at",
    "using", "use", "used", "based", "such", "than", "then", "into", "over", "more", "most", "also",
    "show", "shows", "propose", "proposed", "paper", "method", "results", "approach", "new", "model",
    "models", "learning", "learn", "however", "while", "when", "where", "between",
}


_CJK_RUN = re.compile(r"[\u3400-\u9fff\uf900-\ufaff]+")


def cjk_tokens(text):
    """Character bigrams of each Chinese run; a lone character is too ambiguous to be a term."""
    out = []
    for run in _CJK_RUN.findall(text or ""):
        out.extend(run[i:i + 2] for i in range(len(run) - 1))
    return out


# The short symbols are case-sensitive: plain "li" / "na" / "fe" are not elements.
ELEMENTS = {"Li", "Na", "Fe", "Al", "Si", "Cl", "Mg", "Ca", "Co", "Ni", "Cu", "Zn", "Mn", "Ti"}
GREEK = {"α": "alpha", "β": "beta", "γ": "gamma", "δ": "delta"}


SCIENCE_CACHE_BYTES = 4 * 1024 * 1024
SCIENCE_CACHE_ENTRIES = 128
SCIENCE_CACHE_TEXT_CHARS = 8192
_SCIENCE_CACHE = OrderedDict()
_SCIENCE_CACHE_BYTES = 0
_SCIENCE_LOCK = threading.RLock()


def _scientific_text(text):
    value = unicodedata.normalize("NFKC", text)
    for symbol, name in GREEK.items():
        value = value.replace(symbol, " " + name + " ")
    for symbol in ELEMENTS:
        value = re.sub(r"(?<![A-Za-z0-9-])" + symbol + r"(?![A-Za-z0-9-])", "element_" + symbol, value)
    value = re.sub(r"(?i)(?<![a-z0-9])PD[-_ ]?L[-_ ]?1(?![a-z0-9])", "PD-L1", value)
    value = re.sub(r"(?i)(?<![a-z0-9])PD[-_ ]?1(?![a-z0-9])", "PD-1", value)
    value = re.sub(r"(?i)\banti[-_ ]+(PD-(?:L1|1))\b", r"anti \1", value)
    value = re.sub(r"(?i)\bworld[- ]models?\b", "world model", value)
    value = re.sub(r"(?i)\bsolid[- ]state\b", "solid state", value)
    value = re.sub(r"(?i)\btumour(s)?\b", r"tumor\1", value)
    value = re.sub(r"(?i)\bsulphide(s)?\b", r"sulfide\1", value)
    return value


def scientific_text(text):
    """Same explicit identities, with a byte/entry/length-bounded local cache.

    The 4 MiB accounting includes both strings and 512 bytes per entry for
    dictionary/node bookkeeping. Large source text is never retained here.
    """
    global _SCIENCE_CACHE_BYTES
    value = str(text or '')
    if len(value) > SCIENCE_CACHE_TEXT_CHARS:
        return _scientific_text(value)
    with _SCIENCE_LOCK:
        cached = _SCIENCE_CACHE.get(value)
        if cached is not None:
            _SCIENCE_CACHE.move_to_end(value)
            return cached[0]
    result = _scientific_text(value)
    size = sys.getsizeof(value) + sys.getsizeof(result) + 512
    if size > SCIENCE_CACHE_BYTES:
        return result
    with _SCIENCE_LOCK:
        if value not in _SCIENCE_CACHE:
            while _SCIENCE_CACHE and (len(_SCIENCE_CACHE) >= SCIENCE_CACHE_ENTRIES or
                                      _SCIENCE_CACHE_BYTES + size > SCIENCE_CACHE_BYTES):
                _, (_, old_size) = _SCIENCE_CACHE.popitem(last=False)
                _SCIENCE_CACHE_BYTES -= old_size
            _SCIENCE_CACHE[value] = (result, size)
            _SCIENCE_CACHE_BYTES += size
    return result


def words(text):
    """Lexical terms, including scientific identities; pure numerals stay for retrieval only."""
    value = scientific_text(text)
    elements = re.findall(r"element_([A-Z][a-z])", value)
    value = re.sub(r"element_[A-Z][a-z]", " ", value)
    found = re.findall(r"[a-z0-9][a-z0-9\-]+", value.lower())
    return [w for w in found if len(w) >= 3 and w not in STOPWORDS] + ["element:"+s for s in elements]


def topical_words(text):
    """Display vocabulary excludes measurements and generic academic/action boilerplate."""
    weak = {"acting", "act", "action", "study", "studies", "result", "results", "experiment", "experiments",
            "performance", "demonstrate", "demonstrates", "achieve", "achieves", "novel", "framework", "approach"}
    return [w for w in words(text) if not w.isdigit() and w not in weak]


# PDF text may wrap once inside a phrase; blank lines and paragraph/page
# separators are evidence boundaries, never a way to assemble a phrase.
PHRASE_SEPARATOR = r"(?:[ \t\-]+|[ \t\-]*(?:\r\n|\n|\r|\u2028)[ \t\-]*)"


_CJK_EDGE_SPACE = re.compile(r"(?<=[\u3400-\u9fff\uf900-\ufaff])\s+|\s+(?=[\u3400-\u9fff\uf900-\ufaff])")


def term_in_text(text, term):
    """Whole phrase evidence using the same explicit science identities as the ranker."""
    value, query = scientific_text(text).casefold(), scientific_text(term).casefold().strip()
    if not query:return False
    if cjk_tokens(query):
        # spaces next to a Chinese character carry no meaning ("LLM 推理" and "LLM推理" are the same term)
        return _CJK_EDGE_SPACE.sub("", query) in _CJK_EDGE_SPACE.sub("", value)
    parts=[re.escape(p) for p in re.split(r"[\s\-]+",query) if p]
    return bool(parts and re.search(r"(?<![a-z0-9_])"+PHRASE_SEPARATOR.join(parts)+r"s?(?![a-z0-9_])",value))


def tokenize(text):
    """For similarity: English words as before (unchanged), then Chinese character bigrams."""
    return words(text) + cjk_tokens(text)


def build_idf(token_lists):
    total = len(token_lists)
    df = {}
    for tokens in token_lists:
        for token in set(tokens):
            df[token] = df.get(token, 0) + 1
    return {token: math.log((1 + total) / (1 + count)) + 1.0 for token, count in df.items()}


def vectorize(tokens, idf):
    counts = {}
    for token in tokens:
        counts[token] = counts.get(token, 0) + 1
    return {token: (1.0 + math.log(count)) * idf.get(token, 0.0) for token, count in counts.items()}


def l2_normalize(vector):
    norm = math.sqrt(sum(v * v for v in vector.values()))
    return {k: v / norm for k, v in vector.items()} if norm else dict(vector)


def cosine(a, b):
    if len(a) > len(b):
        a, b = b, a
    return sum(v * b.get(t, 0.0) for t, v in a.items())


def centroid(vectors):
    total = {}
    for vector in vectors:
        for token, value in vector.items():
            total[token] = total.get(token, 0.0) + value
    count = max(len(vectors), 1)
    return l2_normalize({k: v / count for k, v in total.items()})


def rocchio(seed_vectors, pos_vectors, neg_vectors, pos_weight=1.0, neg_weight=0.5, pos_factors=None, neg_factors=None):
    """Seed centroid + positive centroid - negative centroid, clamped to positive weights."""
    combined = {}
    for vectors, weight, factors in ((seed_vectors,1.0,None),(pos_vectors,pos_weight,pos_factors),(neg_vectors,-neg_weight,neg_factors)):
        if not vectors:continue
        if factors is not None:
            adjusted=[{k:v*f for k,v in vec.items()} for vec,f in zip(vectors,factors)]
            direction=centroid(adjusted)
            weight*=sum(factors)/len(factors)
        else:direction=centroid(vectors)
        for token, value in direction.items():
            combined[token] = combined.get(token, 0.0) + weight * value
    return l2_normalize({k: v for k, v in combined.items() if v > 0})


def profile_terms(profile, limit=40):
    return [token for token, _ in sorted(profile.items(), key=lambda kv: -kv[1])[:limit]]


def mmr_select(scored, vectors, k, lambda_=0.8):
    """Maximum marginal relevance: relevance minus redundancy, deterministic.

    scored: list of (key, relevance) sorted or unsorted; vectors: key -> sparse vector.
    """
    selected, remaining = [], list(scored)
    while remaining and len(selected) < k:
        best, best_value = None, None
        for key, relevance in remaining:
            redundancy = max((cosine(vectors[key], vectors[chosen]) for chosen in selected), default=0.0)
            value = lambda_ * relevance - (1 - lambda_) * redundancy
            if best_value is None or value > best_value:
                best, best_value = key, value
        selected.append(best)
        remaining = [(key, relevance) for key, relevance in remaining if key != best]
    return selected


def sort_scored(scored, published):
    """Order (key, score) pairs by score, then newest first, then key, so equal scores are not left to chance.

    A profile that shares no vocabulary with the candidates scores everything 0; without an explicit
    tie-break the order would be whatever the database returned.
    """
    ordered = sorted(scored, key=lambda kv: kv[0])
    ordered.sort(key=lambda kv: published.get(kv[0]) or "", reverse=True)
    ordered.sort(key=lambda kv: -kv[1])
    return ordered


def rank_candidates(profile, candidate_vectors):
    return sorted(candidate_vectors, key=lambda kv: -cosine(profile, kv[1]))


def novelty_score(relevance, published, boost=0, today=None):
    """Bounded recency multiplier: never promotes a zero-relevance paper or a future date."""
    import datetime
    try:
        day=datetime.date.fromisoformat(str(published))
        current=datetime.date.fromisoformat(str(today)) if today else datetime.date.today()
    except (ValueError,TypeError):return relevance
    age=(current-day).days
    return relevance if age<0 else relevance*(1+boost*math.exp(-age/30))

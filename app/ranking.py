"""Sparse lexical ranking and a transparent, editable profile vector.

Deterministic, zero model tokens, offline. BM25-style is not needed at this
corpus size; TF-IDF cosine plus a Rocchio-style relevance-feedback profile is
enough and easy to explain.
"""
import math
import re

STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "we", "our", "is", "are",
    "that", "this", "as", "by", "from", "it", "its", "be", "can", "which", "these", "their", "at",
    "using", "use", "used", "based", "such", "than", "then", "into", "over", "more", "most", "also",
    "show", "shows", "propose", "proposed", "paper", "method", "results", "approach", "new", "model",
    "models", "learning", "learn", "however", "while", "when", "where", "between",
}


def tokenize(text):
    words = re.findall(r"[a-z0-9][a-z0-9\-]+", (text or "").lower())
    return [w for w in words if len(w) >= 3 and w not in STOPWORDS]


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


def rocchio(seed_vectors, pos_vectors, neg_vectors, pos_weight=1.0, neg_weight=0.5):
    """Seed centroid + positive centroid - negative centroid, clamped to positive weights."""
    combined = {}
    for vectors, weight in ((seed_vectors, 1.0), (pos_vectors, pos_weight), (neg_vectors, -neg_weight)):
        if not vectors:
            continue
        for token, value in centroid(vectors).items():
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


def rank_candidates(profile, candidate_vectors):
    return sorted(candidate_vectors, key=lambda kv: -cosine(profile, kv[1]))

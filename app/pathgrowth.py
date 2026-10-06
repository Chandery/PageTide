"""Attaching papers to concepts, checking edges against the corpus, and counting the evidence for a new branch.

Deterministic and local: no model, no network, no clock, no randomness. Whether a group of collected papers is a new
direction, and what to call it, is the model's opinion (operation direction_judge, one click); this module only counts
what is under a stored direction and never adds anything to the map by itself; a person confirms (PRODUCT: the
profile is data you can check and correct).

The thresholds are proposals without data behind them (named constants, to be tuned on replay):
a branch needs several distinct papers, explicit positive evidence and more than one source (the gates),
and a strength score S * C * (0.5 + 0.5 * R): enough independent evidence (S), papers that read alike (C) and recent
activity (R). "Not already on the map" is the model's judgement, backed by a local check (T_NEAR).
"""
import functools
import math
import re

from . import eligibility, pathgraph, ranking

MIN_STRENGTH = 0.25
MIN_MEMBERS = 3          # distinct papers in the cluster
MIN_POSITIVE = 2         # of which explicitly positive (saved / useful / seed)
MIN_SOURCES = 2          # distinct journals / venues
MAX_CANDIDATES = 5
RECENT_ACTIVE_DAYS = 30  # "recent" counts active days with evidence, not calendar days
SUPPORT_MARGIN = 0.15
_INTRO = re.compile(r"\b(survey|review|tutorial|introduction|intro|primer|overview|handbook|textbook|lecture notes|a gentle)\b")
_INTRO_CJK = ("综述", "教程", "入门", "概述", "导论", "综论")


# ------------------------------------------------------------------ matching
@functools.lru_cache(maxsize=2048)
def _pattern(term):
    parts = [re.escape(p) for p in re.split(r"[\s\-]+", term) if p]
    if not parts:
        return re.compile(r"(?!)")   # a term of separators only matches nothing
    return re.compile(r"(?<![a-z0-9])" + r"[\s\-]+".join(parts) + r"s?(?![a-z0-9])")


def term_in_text(text, term):
    """Whole-word match (case, hyphen/space and a plural 's' tolerated); Chinese terms match as substrings."""
    term = re.sub(r"\s+", " ", str(term or "").strip().lower())
    if not term:
        return False
    text = str(text or "").lower()
    if ranking.cjk_tokens(term):
        return term in text
    return _pattern(term).search(text) is not None


def _text(paper):
    return eligibility.retrieval_text(paper)


def assign(graph, papers):
    """{paper_key: [concept ids]}: the (at most two) concepts whose terms a paper uses, best first.
    Title hits count double. Derived, never stored: it must not rewrite anyone's own classification."""
    out = {}
    concepts = [c for c in graph["concepts"] if c.get("state") != "archived" and c.get("terms")]
    for paper in papers:
        if not paper.get("key"):
            continue
        text, title = _text(paper), paper.get("title") or ""
        scored = []
        for index, c in enumerate(concepts):
            hits = sum(term_in_text(text, t) for t in c["terms"])
            if hits:
                scored.append((-(hits + sum(term_in_text(title, t) for t in c["terms"])), index, c["id"]))
        if scored:
            out[paper["key"]] = [cid for _, _, cid in sorted(scored)[:2]]
    return out


def paper_role(paper):
    """"intro" for surveys, tutorials and primers (read first inside a concept), else "advanced"."""
    title = str(paper.get("title") or "").lower()
    return "intro" if _INTRO.search(title) or any(w in title for w in _INTRO_CJK) else "advanced"


# ------------------------------------------------------------------- support
def edge_support(u_docs, v_docs, u_terms, v_terms, min_docs=3):
    """How much the corpus agrees that u comes before v: the share of v's documents that mention u's terms
    minus the share of u's documents that mention v's terms (the asymmetric-reference idea of RefD / ACE,
    on local text). Positive supports the direction, negative suggests it is reversed. None = too little text."""
    if len(u_docs) < min_docs or len(v_docs) < min_docs or not u_terms or not v_terms:
        return None
    forward = sum(any(term_in_text(d, t) for t in u_terms) for d in v_docs) / len(v_docs)
    backward = sum(any(term_in_text(d, t) for t in v_terms) for d in u_docs) / len(u_docs)
    return round(forward - backward, 4)


def support_label(value, margin=SUPPORT_MARGIN):
    if value is None:
        return "unknown"
    if value >= margin:
        return "supported"
    if value <= -margin:
        return "contradicted"
    return "neutral"


def annotate_support(graph, docs_by_concept, min_docs=3):
    """A copy of the graph with each edge's `support` filled in (None when there is too little text)."""
    out = pathgraph.copy.deepcopy(graph)
    terms = {c["id"]: c["terms"] for c in out["concepts"]}
    for edge in out["prereqs"]:
        edge["support"] = edge_support(docs_by_concept.get(edge["from"], []), docs_by_concept.get(edge["to"], []),
                                       terms.get(edge["from"], []), terms.get(edge["to"], []), min_docs)
    return out


# ---------------------------------------------------------------------- gaps
def covered_tokens(graph):
    tokens = set()
    for c in graph["concepts"]:
        tokens.update(ranking.words(c["name"] + " " + " ".join(c["terms"])))
    return tokens


def gap_terms(text, covered, idf, limit=3):
    """Terms of a paper (typically one marked too hard) that no concept covers, rarest first: the raw
    material for a "missing prerequisite" suggestion."""
    words = [w for w in dict.fromkeys(ranking.words(text)) if w not in covered]
    return sorted(words, key=lambda w: (-idf.get(w, 0.0), w))[:limit]


# -------------------------------------------------------------------- growth
# Potential directions are found by the model (operation direction_judge) from the exploration papers the reader
# collected. This module only counts: how many papers, how many the reader explicitly marked, how many sources, and how
# consistent the papers read. Nothing here decides that something is a direction, and nothing is merged by itself.
T_NEAR = 0.40            # a group whose papers read this much like a concept already on the map is that concept, not a new direction
T_TOWARD = 0.20          # a paper this close to a direction's papers may be offered by an exploration slot


def _identity(paper):
    """What makes two records the same paper: its DOI, else its normalised title (arXiv and journal copies)."""
    doi = str(paper.get("doi") or "").strip().lower().replace("https://doi.org/", "")
    return ("doi", doi) if doi else ("title", pathgraph._key(paper.get("title")) or paper.get("key"))


def paper_vectors(papers, idf=None):
    """{key: unit vector of the paper's title and abstract}; the idf is the papers' own unless one is given."""
    tokens = {p["key"]: ranking.tokenize(_text(p)) for p in papers if p.get("key")}
    idf = idf or ranking.build_idf(list(tokens.values()))
    return {k: ranking.l2_normalize(ranking.vectorize(t, idf)) for k, t in tokens.items()}, idf


def centroid(vectors):
    total = {}
    for vector in vectors:
        for token, weight in vector.items():
            total[token] = total.get(token, 0.0) + weight
    return ranking.l2_normalize(total)


def rank_concepts(graph, papers, member_keys, vectors, idf):
    """[(concept id, cosine)] best first: how much each concept of the map (its name, terms and the papers that use its terms)
    reads like the member papers. Local and deterministic."""
    members = [vectors[k] for k in member_keys if k in vectors]
    if not members:
        return []
    mine = centroid(members)
    assigned = assign(graph, papers)
    out = []
    for concept in sorted((c for c in graph["concepts"] if c.get("state") != "archived"), key=lambda c: c["id"]):
        docs = [vectors[k] for k, ids in sorted(assigned.items()) if concept["id"] in ids and k in vectors and k not in member_keys][:8]
        own = ranking.l2_normalize(ranking.vectorize(ranking.tokenize(concept["name"] + " " + " ".join(concept.get("terms") or [])), idf))
        out.append((concept["id"], round(ranking.cosine(mine, centroid(docs + [own] * 2)), 4)))
    return sorted(out, key=lambda t: (-t[1], t[0]))


def nearest_concept(graph, papers, member_keys, vectors, idf):
    """(concept id | None, cosine): the concept of the map the member papers read most like; used as a backstop against
    calling a neighbour new."""
    ranked = rank_concepts(graph, papers, member_keys, vectors, idf)
    return ranked[0] if ranked else (None, 0.0)


def rank_directions(directions, member_keys, vectors):
    """The stored directions, the one whose papers read most like the member papers first (ties by id)."""
    members = [vectors[k] for k in member_keys if k in vectors]
    mine = centroid(members) if members else {}
    def value(direction):
        own = [vectors[k] for k in direction.get("papers", []) if k in vectors]
        return ranking.cosine(mine, centroid(own)) if own and mine else 0.0
    return sorted(directions, key=lambda d: (-round(value(d), 4), d["id"]))


def direction_evidence(member_keys, papers, positive, vectors, recent_days=RECENT_ACTIVE_DAYS):
    """What a stored direction has so far, counted from the papers the model put under it.

    positive: {paper_key: ISO day of the explicit positive event, or None}. The four gates are the same as ever
    (>= MIN_MEMBERS distinct papers, >= MIN_POSITIVE of them explicitly positive, >= MIN_SOURCES sources, and strength
    S * C * (0.5 + 0.5 * R) >= MIN_STRENGTH). That the group is clearly different from the map is the model's judgement,
    not a measured part. `ready` when all are met."""
    by_key = {p["key"]: p for p in papers if p.get("key")}
    keys = sorted(k for k in set(member_keys) if k in by_key)
    ident = {k: _identity(by_key[k]) for k in keys}
    distinct = lambda ks: len({ident[k] for k in ks})
    positives_in = [k for k in keys if k in positive]
    n_papers, n_positive = distinct(keys), distinct(positives_in)
    sample = (positives_in + [k for k in keys if k not in positive])[:12]
    pairs = [(a, b) for i, a in enumerate(sample) for b in sample[i + 1:] if a in vectors and b in vectors]
    coherence = sum(ranking.cosine(vectors[a], vectors[b]) for a, b in pairs) / len(pairs) if pairs else 0.0
    active = sorted({str(d) for d in positive.values() if d})
    recent = set(active[-recent_days:])
    mine = [k for k in positives_in if str(positive[k]) in recent]
    recency = len(mine) / len(positives_in) if positives_in else 0.0
    support = 1.0 - math.exp(-n_positive / 3.0)
    strength = support * coherence * (0.5 + 0.5 * recency)
    sources = {str(by_key[k].get("source") or "").strip().lower() for k in keys} - {""}
    gates = {"papers": n_papers >= MIN_MEMBERS, "positive": n_positive >= MIN_POSITIVE, "sources": len(sources) >= MIN_SOURCES}
    return {"papers": keys, "positive": positives_in, "strength": round(strength, 4),
            "parts": {"S": round(support, 4), "C": round(coherence, 4), "R": round(recency, 4)},
            "counts": {"papers": n_papers, "positive": n_positive, "sources": len(sources)}, "source_names": sorted(sources),
            "gates": gates, "status": "ready" if all(gates.values()) and round(strength, 4) >= MIN_STRENGTH else "watch"}


def toward_directions(directions, vectors, pool_keys, limit=5):
    """For an exploration slot: [{"name", "papers": [keys of the pool, best first]}], the papers of the pool that read like the
    papers already under a stored direction (cosine to their centroid >= T_TOWARD). Local; reads no clock."""
    out = []
    for direction in directions:
        members = [vectors[k] for k in direction["papers"] if k in vectors]
        if not members:
            continue
        mine = centroid(members)
        scored = sorted(((ranking.cosine(mine, vectors[k]), k) for k in sorted(pool_keys) if k in vectors and k not in direction["papers"]), key=lambda t: (-t[0], t[1]))
        out.append({"name": direction["name"], "papers": [k for value, k in scored if value >= T_TOWARD][:limit]})
    return out


def merge_candidate(graph, candidate):
    """A copy of the graph with the stored direction added as a *proposed* grown concept (and its proposed edges): the
    model's name, the English search terms, its short intro (marked as the model's) and its prerequisites among the
    concepts already there. Idempotent: a direction already on the map (by id) is not added twice. The caller shows it
    with its evidence; only a person confirms it."""
    if any(c.get("candidate") == candidate.get("id") for c in graph["concepts"]):
        return pathgraph.copy.deepcopy(graph)
    hints = {c["id"]: c["hint"] for c in graph["concepts"]}
    needs = [p["from"] for p in candidate.get("prereqs", []) if p["from"] in hints]
    # A prerequisite that is already an ancestor of another proposed one is implied by it: propose only the nearer one.
    needs = [n for n in needs if not any(n in pathgraph.ancestors(graph, [m]) for m in needs if m != n)]
    intro = "；".join(x for x in (str(candidate.get("intro") or "").strip(), ("门槛：" + str(candidate["barrier"]).strip()) if candidate.get("barrier") else "") if x)
    merged = pathgraph.add_concept(
        graph, {"name": candidate["name"], "terms": candidate["terms"], "hint": max([hints[n] for n in needs], default=2),
                "origin": "grown", "state": "proposed", "intro": intro, "intro_by": "ai"}, needs=needs)
    added = merged["concepts"][-1]
    added["candidate"] = candidate.get("id")
    added["evidence"] = list(candidate.get("papers", []))[:12]
    for edge in merged["prereqs"]:
        if edge["to"] == added["id"]:
            edge["support"] = None
    return merged

"""Attaching papers to concepts, checking edges against the corpus, and proposing new branches.

Deterministic and local: no model, no network, no clock, no randomness. Everything here only *proposes*;
a person confirms before the map changes (PRODUCT: the profile is data you can check and correct).

The thresholds are proposals without data behind them (named constants, to be tuned on replay):
a branch needs several distinct papers, explicit positive evidence and more than one source (the gates),
and a strength score S * C * (0.5 + 0.5 * R) * N, built from signals the literature uses for "emerging topic"
detection: enough independent evidence (S), a coherent cluster (C), recent activity (R), and not already
on the map (N).
"""
import functools
import hashlib
import math
import re

from . import pathgraph, ranking

MIN_STRENGTH = 0.25
MIN_MEMBERS = 3          # distinct papers in the cluster
MIN_POSITIVE = 2         # of which explicitly positive (saved / useful / seed)
MIN_SOURCES = 2          # distinct journals / venues
MAX_CANDIDATES = 5
MAX_PHRASES = 60
RECENT_ACTIVE_DAYS = 30  # "recent" counts active days with evidence, not calendar days
SUPPORT_MARGIN = 0.15
BROADER = 1.5            # a concept this much larger than the cluster makes it a specialisation, not a duplicate
MIN_NOVELTY = 0.2
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
    return f"{paper.get('title') or ''} {paper.get('abstract') or ''}"


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
_WORD = re.compile(r"[a-z0-9][a-z0-9\-]+")


def _sequence(text):
    return _WORD.findall(str(text or "").lower())


def _content(word):
    return len(word) >= 3 and word not in ranking.STOPWORDS


def _bigrams(sequence):
    """Adjacent content-word pairs of the raw text. A stopword between two words ("policy for robot") breaks the
    pair, so every phrase proposed here is something term_in_text() can find again in the paper."""
    return {(a, b) for a, b in zip(sequence, sequence[1:]) if _content(a) and _content(b)}


def _identity(paper):
    """What makes two records the same paper: its DOI, else its normalised title (arXiv and journal copies)."""
    doi = str(paper.get("doi") or "").strip().lower().replace("https://doi.org/", "")
    return ("doi", doi) if doi else ("title", pathgraph._key(paper.get("title")) or paper.get("key"))


def _jaccard(a, b):
    return len(a & b) / len(a | b) if a | b else 0.0


def branch_candidates(graph, papers, positive, recent_days=RECENT_ACTIVE_DAYS, min_members=MIN_MEMBERS, limit=MAX_CANDIDATES):
    """Proposed new branches from the papers the reader responded to.

    papers: every paper of the project [{key, title, abstract, source}].
    positive: {paper_key: ISO day of the explicit positive event, or None} for saved / useful / seed papers.

    A candidate is a phrase shared by several of the positive papers; its cluster is every paper containing
    it. It is `ready` when the gates pass (>= 3 papers, >= 2 positive, >= 2 sources) and
    strength = S * C * (0.5 + 0.5 * R) * N reaches MIN_STRENGTH; otherwise `watch`. Clusters already covered
    by the map (N < MIN_NOVELTY) are not listed. Nothing is merged here.

    `min_members` is how many papers a phrase must be in to be listed at all. It stays MIN_MEMBERS for deciding
    what can be added; a page that wants to show a direction while it is still forming passes 2, and such a
    candidate is always "watch" (the papers gate asks for MIN_MEMBERS). `counts` and `source_names` say what
    each gate has so far.
    """
    by_key = {p["key"]: p for p in papers if p.get("key")}
    pos = sorted(k for k in positive if k in by_key)
    if not pos:
        return []
    keys = sorted(by_key)
    ident = {k: _identity(by_key[k]) for k in keys}
    distinct = lambda ks: len({ident[k] for k in ks})
    texts = {k: _text(by_key[k]) for k in keys}
    idf = ranking.build_idf([ranking.tokenize(texts[k]) for k in keys])
    vectors = {k: ranking.l2_normalize(ranking.vectorize(ranking.tokenize(texts[k]), idf)) for k in keys}
    grams = {k: _bigrams(_sequence(texts[k])) for k in keys}
    title_seq = {k: _sequence(by_key[k].get("title")) for k in keys}
    mentions = {}

    def has(key, term):
        if (key, term) not in mentions:
            mentions[(key, term)] = term_in_text(texts[key], term)
        return mentions[(key, term)]

    # phrases shared by several distinct positive papers (a paper under two keys counts once)
    counts, seen_ident = {}, set()
    for k in pos:
        if ident[k] in seen_ident:
            continue
        seen_ident.add(ident[k])
        for gram in grams[k]:
            counts[gram] = counts.get(gram, 0) + 1
    phrases = sorted((g for g, n in counts.items() if n >= MIN_POSITIVE), key=lambda g: (-counts[g], g))
    wanted = set(phrases)
    index = {}
    for k in keys:
        for gram in grams[k] & wanted:
            index.setdefault(gram, []).append(k)
    members = {}
    size = {gram: distinct(index.get(gram, [])) for gram in phrases}
    # Phrases that already meet the member gate come first, so a looser display threshold (2) cannot crowd a ready
    # direction out of the MAX_PHRASES cap with alphabetically earlier two-paper phrases.
    for gram in sorted(phrases, key=lambda g: (size[g] < MIN_MEMBERS, -counts[g], g)):
        if size[gram] >= min_members:
            members[gram] = index[gram]
        if len(members) >= MAX_PHRASES:
            break

    concept_docs = {c["id"]: {k for k in keys if any(has(k, t) for t in c["terms"])}
                    for c in graph["concepts"] if c.get("terms") and c.get("state") != "archived"}
    levels = pathgraph.layers(graph)
    active = sorted({str(d) for d in positive.values() if d})
    recent = set(active[-recent_days:])
    clean_source = lambda k: str(by_key[k].get("source") or "").strip().lower()

    def support_of(u_keys, v_keys, u_terms, v_terms):
        if len(u_keys) < 3 or len(v_keys) < 3 or not u_terms or not v_terms:
            return None
        forward = sum(any(has(k, t) for t in u_terms) for k in v_keys) / len(v_keys)
        backward = sum(any(has(k, t) for t in v_terms) for k in u_keys) / len(u_keys)
        return round(forward - backward, 4)

    found = []
    for gram in sorted(members, key=lambda g: (-counts[g], -len(members[g]), g)):
        cluster = members[gram]
        cluster_set = set(cluster)
        positives_in = [k for k in cluster if k in positive]
        n_cluster, n_positive = distinct(cluster), distinct(positives_in)
        # novelty: how much of the cluster the map already covers
        best_id, best_cover = None, 0.0
        for cid in sorted(concept_docs):
            cover = len(cluster_set & concept_docs[cid]) / len(cluster)
            if cover > best_cover:
                best_id, best_cover = cid, cover
        if best_cover >= 0.5 and best_id is not None and len(concept_docs[best_id]) >= BROADER * len(cluster):
            novelty = 0.6   # a specialisation of a broader concept
        else:
            novelty = 1.0 - best_cover
        if novelty < MIN_NOVELTY:
            continue
        sample = (positives_in + [k for k in cluster if k not in positive])[:12]
        pairs = [(a, b) for i, a in enumerate(sample) for b in sample[i + 1:]]
        coherence = sum(ranking.cosine(vectors[a], vectors[b]) for a, b in pairs) / len(pairs) if pairs else 0.0
        mine = [k for k in positives_in if str(positive[k]) in recent]
        recency = len(mine) / len(positives_in) if positives_in else 0.0
        support = 1.0 - math.exp(-n_positive / 3.0)
        strength = support * coherence * (0.5 + 0.5 * recency) * novelty
        sources = {clean_source(k) for k in cluster if clean_source(k)}
        gates = {"papers": n_cluster >= MIN_MEMBERS, "positive": n_positive >= MIN_POSITIVE, "sources": len(sources) >= MIN_SOURCES}

        phrase = " ".join(gram)
        # A phrase that leads many titles names the topic better than one found only in abstracts.
        in_titles = [title_seq[k] for k in cluster if gram in _bigrams(title_seq[k])]
        lead = sum(next(i for i, pair in enumerate(zip(t, t[1:])) if pair == gram) for t in in_titles) / len(in_titles) if in_titles else 99.0
        terms = [phrase]

        parent = None
        for cid in sorted(concept_docs, key=lambda c: (len(concept_docs[c]), c)):
            if len(cluster_set & concept_docs[cid]) / len(cluster) >= 0.8 and len(concept_docs[cid]) > len(cluster):
                parent = cid
                break
        prereqs = []
        for cid in sorted(concept_docs):
            others = sorted(concept_docs[cid] - cluster_set)
            concept = next(c for c in graph["concepts"] if c["id"] == cid)
            value = support_of(others, cluster, concept["terms"], terms)
            if value is not None and value >= SUPPORT_MARGIN:
                prereqs.append({"from": cid, "support": value})
        prereqs = sorted(prereqs, key=lambda p: (-p["support"], p["from"]))[:3]
        layer = 1 + max((levels.get(p["from"], 1) for p in prereqs), default=0)

        found.append({"id": "g-" + hashlib.sha1("|".join(cluster).encode()).hexdigest()[:10], "name": phrase, "terms": terms,
                      "papers": cluster, "positive": positives_in, "strength": round(strength, 4),
                      "parts": {"S": round(support, 4), "C": round(coherence, 4), "R": round(recency, 4), "N": round(novelty, 4)},
                      "counts": {"papers": n_cluster, "positive": n_positive, "sources": len(sources)}, "source_names": sorted(sources),
                      "gates": gates, "status": "ready" if all(gates.values()) and round(strength, 4) >= MIN_STRENGTH else "watch",
                      "parent": parent, "prereqs": prereqs, "layer": layer, "_rank": (-len(in_titles), lead)})

    # One candidate per set of papers. Phrases whose papers overlap by >= 0.8 describe the same branch: keep the
    # best-evidenced one (then the one leading most titles, then earliest in the title), and use the next best
    # phrase of the same branch as its second search term.
    found.sort(key=lambda c: (-len(c["positive"]), -len(c["papers"]), c["_rank"], c["name"]))
    kept = []
    for cand in found:
        twin = next((k for k in kept if _jaccard(set(cand["papers"]), set(k["papers"])) >= 0.8), None)
        if twin is None:
            kept.append(cand)
        elif len(twin["terms"]) < 2 and cand["name"] not in twin["name"] and twin["name"] not in cand["name"]:
            twin["terms"].append(cand["name"])
    for cand in kept:
        cand.pop("_rank", None)
    return sorted(kept, key=lambda c: (-c["strength"], c["name"]))[:limit]


def merge_candidate(graph, candidate):
    """A copy of the graph with the candidate added as a *proposed* grown concept (and its proposed edges).
    Idempotent: a candidate already on the map (by id) is not added twice. Edges that a longer path implies
    are dropped by add_concept. The caller shows it with its evidence; only a person confirms it."""
    if any(c.get("candidate") == candidate.get("id") for c in graph["concepts"]):
        return pathgraph.copy.deepcopy(graph)
    hints = {c["id"]: c["hint"] for c in graph["concepts"]}
    needs = [p["from"] for p in candidate.get("prereqs", []) if p["from"] in hints]
    # A prerequisite that is already an ancestor of another proposed one is implied by it: propose only the nearer one.
    needs = [n for n in needs if not any(n in pathgraph.ancestors(graph, [m]) for m in needs if m != n)]
    merged = pathgraph.add_concept(
        graph, {"name": candidate["name"], "terms": candidate["terms"], "hint": max([hints[n] for n in needs], default=2),
                "origin": "grown", "state": "proposed"}, needs=needs)
    added = merged["concepts"][-1]
    added["parent"] = candidate.get("parent")
    added["candidate"] = candidate.get("id")
    added["evidence"] = list(candidate.get("papers", []))[:12]
    supports = {p["from"]: p["support"] for p in candidate.get("prereqs", [])}
    for edge in merged["prereqs"]:
        if edge["to"] == added["id"]:
            edge["support"] = supports.get(edge["from"])
    return merged

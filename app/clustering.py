"""Bounded, offline lexical communities; no model calls or implicit fallback.

Results are deterministic for a fixed NetworkX version. Edges are similarities,
not citations or evidence of agreement. Notes never enter the corpus.
"""
import hashlib
import json

from . import ranking

MAX_PAPERS = 2000
MAX_TEXT = 50000
ALGORITHM = "tfidf-louvain-v1"


class ClusteringUnavailable(RuntimeError):
    """Install NetworkX with louvain_communities to enable the relation graph."""


def _corpus(papers):
    rows = [{field: paper.get(field) or "" for field in
             ("key", "title", "abstract", "topic")} for paper in papers]
    if any(not isinstance(value, str) for row in rows for value in row.values()):
        raise ValueError("Corpus fields must be strings")
    if any(not row["key"] for row in rows) or len({r["key"] for r in rows}) != len(rows):
        raise ValueError("Corpus keys must be nonempty and unique")
    return sorted(rows, key=lambda row: row["key"])


def corpus_fingerprint(papers):
    payload = json.dumps(_corpus(papers), sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def cluster(papers):
    """Return fingerprint, groups, similarity edges and reproducibility metadata.

    At most eight neighbors per node are selected (undirected union), with
    cosine >= .15. Pairwise comparisons are quadratic; reject oversized inputs
    explicitly instead of silently sampling or truncating them.
    """
    rows = _corpus(papers)
    if len(rows) > MAX_PAPERS:
        raise ValueError("Clustering supports at most %d saved papers" % MAX_PAPERS)
    if any(sum(len(row[f]) for f in ("title", "abstract", "topic")) > MAX_TEXT for row in rows):
        raise ValueError("Paper text exceeds clustering limit")
    try:
        import networkx as nx
        louvain = nx.community.louvain_communities
    except (ImportError, AttributeError) as exc:
        raise ClusteringUnavailable(
            "The relation graph requires NetworkX with community.louvain_communities; no alternative was run"
        ) from exc
    tokens = [ranking.tokenize(" ".join(row[f] for f in ("title", "abstract", "topic")))
              for row in rows]
    idf = ranking.build_idf(tokens)
    vectors = [ranking.l2_normalize(ranking.vectorize(t, idf)) for t in tokens]
    graph = nx.Graph()
    keys = [row["key"] for row in rows]
    graph.add_nodes_from(keys)
    neighbors = [[] for _ in keys]
    for i, key in enumerate(keys):
        for j in range(i + 1, len(keys)):
            weight = ranking.cosine(vectors[i], vectors[j])
            if weight >= .15:
                neighbors[i].append((weight, keys[j]))
                neighbors[j].append((weight, key))
                # Keep memory bounded even for a fully connected corpus.
                for index in (i, j):
                    neighbors[index].sort(key=lambda pair: (-pair[0], pair[1]))
                    del neighbors[index][8:]
    edges = {}
    for key, entries in zip(keys, neighbors):
        for weight, other in entries:
            edges[tuple(sorted((key, other)))] = weight
    for (left, right), weight in sorted(edges.items()):
        graph.add_edge(left, right, weight=weight)
    isolated = sorted(nx.isolates(graph))
    active = graph.subgraph([key for key in keys if graph.degree(key)]).copy()
    communities = louvain(active, seed=0, weight="weight", resolution=1) if active.number_of_edges() else []
    communities = sorted([sorted(c) for c in communities] + [[key] for key in isolated])
    by_key = dict(zip(keys, vectors))
    groups = []
    for members in communities:
        weights = {}
        for key in members:
            for term, value in by_key[key].items():
                weights[term] = weights.get(term, 0) + value
        terms = sorted(weights, key=lambda term: (-weights[term], term))[:3]
        digest = hashlib.sha256(json.dumps(members).encode()).hexdigest()[:20]
        groups.append({"id": "cluster-" + digest, "name": " / ".join(terms) or "Unclassified",
                       "keys": members, "terms": terms})
    return {"fingerprint": corpus_fingerprint(rows), "algorithm": ALGORITHM,
            "networkx_version": nx.__version__, "groups": groups,
            "edges": [{"source": a, "target": b, "weight": w, "kind": "similarity"}
                      for (a, b), w in sorted(edges.items())]}

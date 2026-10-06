"""Local, bounded query planning and temporary discovery provenance.

No source calls, model calls, feedback mutation, or permanent paper category.
Search phrases are public terms; private seed/profile IDs never become queries.
"""
import hashlib
import json
import math

from .sources import clean_query

KINDS = ("path", "explore", "watch")
MAX_THEMES = 3
MAX_SOURCE_PAPERS = 600
MAX_PAPER_SOURCES = 3
# 40 saved concepts: at most 40 path keys + 80 target terms + 3 project
# terms + 6 interest terms = 129 paged keys. Leave bounded headroom.
MAX_PAGE_KEYS = 160
MAX_SOURCE_PAGE = 100
SOURCE_TTL = 7 * 24 * 3600


def _number(value, default=0):
    if isinstance(value, int) and not isinstance(value, bool): return value
    return value if isinstance(value, float) and math.isfinite(value) else default


def plan(route, keywords, interest, state=None, language_revision=0,
         basic_since=None, recent_since=None, to_date=None, per_page=50, window_policy=None):
    """Rotate within each purpose, then share at most three distinct themes.

    One first turn per available purpose; unused turns go to another purpose.
    Equal phrases with the same retrieval and pagination strategy merge reasons.
    Foundation, recent exploration and watched updates need separate executions,
    all within the three cap.
    Page progression is based on fetched results, not local keyword-match counts.
    Watched directions always start at page one to check newest publications.
    """
    state = state if isinstance(state, dict) else {}
    by_id = {c["id"]: c for c in route["graph"]["concepts"] if c.get("state", "active") == "active"}
    groups, buckets = {}, {kind: [] for kind in KINDS}

    def add(kind, text, origin, concept=None):
        query = clean_query(text)
        if not query:
            return
        order = "relevance" if kind == "path" else "recent"
        page_mode = "latest" if kind == "watch" else "paged"
        key = query.casefold() + '|' + order + '|' + page_mode
        item = groups.setdefault(key, {"query": query, "order": order, "page_mode": page_mode,
                                       "kinds": [], "concepts": [], "origins": []})
        if kind not in item["kinds"]: item["kinds"].append(kind)
        if concept and concept not in item["concepts"]: item["concepts"].append(concept)
        if origin not in item["origins"]: item["origins"].append(origin)
        if key not in buckets[kind]: buckets[kind].append(key)

    if route.get("goal_status") == "learning":
        for cid in route.get("frontier") or []:
            terms = by_id.get(cid, {}).get("terms") or []
            if terms: add("path", terms[0], "frontier", cid)
    for text in keywords[:3]: add("explore", text, "project_terms")
    for cid in route.get("goal_targets") or []:
        for text in (by_id.get(cid, {}).get("terms") or [])[:2]: add("explore", text, "target_edge", cid)
    for cid, concept in by_id.items():
        if cid not in (route.get("goal_scope") or []) and concept.get("terms"):
            add("explore", concept["terms"][0], "side_branch", cid)
    for text in interest[:6]: add("explore", text, "positive_metadata")
    for cid in route.get("watched_satisfied") or []:
        terms = by_id.get(cid, {}).get("terms") or []
        if terms: add("watch", terms[0], "watched_satisfied", cid)

    per_page = max(1, min(50, int(per_page)))
    # Organization revision also changes for notes/categories/layout. Recall
    # follows the actual route, not unrelated organization edits.
    contract = {"graph": route['graph'], "watch": route.get('watch', []),
                "goal_status": route.get("goal_status"), "goal_scope": route.get('goal_scope', []),
                "buckets": buckets, "groups": groups, "language_revision": language_revision,
                "per_page": per_page, "windows": window_policy if window_policy is not None else
                {"basic_since": basic_since, "recent_since": recent_since, "to_date": to_date}}
    signature = hashlib.sha256(json.dumps(contract, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    # New usefulness can change exploration terms every day. That expires
    # explanation provenance, but must not send unchanged path queries back to
    # page one. Graph/language/window/size changes still reset paging.
    page_contract = {k: v for k, v in contract.items() if k not in ('buckets', 'groups')}
    pagination_signature = hashlib.sha256(json.dumps(page_contract, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    previous = state if state.get('pagination_signature') == pagination_signature else {}
    old_cursors = state.get("cursors") if isinstance(state.get("cursors"), dict) else {}
    cursors = {kind: max(0, int(_number(old_cursors.get(kind)))) for kind in KINDS}
    selected, purpose = [], {}
    while len(selected) < MAX_THEMES:
        changed = False
        for kind in KINDS:
            values = buckets[kind]
            for _ in range(len(values)):
                key = values[cursors[kind] % len(values)]
                cursors[kind] += 1
                if key not in selected:
                    selected.append(key); purpose[key] = kind; changed = True
                    break
            if len(selected) == MAX_THEMES: break
        if not changed: break
    pages = previous.get("pages") if isinstance(previous.get("pages"), dict) else {}
    queries = []
    for key in selected:
        item = {**groups[key], "kind": purpose[key]}
        path = "path" in item["kinds"]
        item.update(order="relevance" if path else "recent", from_date=basic_since if path else recent_since,
                    to_date=to_date, per_page=per_page)
        item["page_key"] = key
        item["page"] = 1 if item['page_mode'] == 'latest' else max(1, min(MAX_SOURCE_PAGE, int(_number(pages.get(item["page_key"]), 1))))
        queries.append(item)
    cursors = {kind: cursors[kind] % max(1, len(buckets[kind])) for kind in KINDS}
    return {"signature": signature, "pagination_signature": pagination_signature,
            "cursors": cursors, "queries": queries}


def live_sources(state, signature, moment):
    """Only current-context, recent provenance. A backwards clock expires it."""
    if not isinstance(state, dict) or state.get("signature") != signature:
        return {}
    stored = state.get("sources") if isinstance(state.get("sources"), dict) else {}
    out = {}
    for key, entries in list(stored.items())[-MAX_SOURCE_PAPERS:]:
        if not isinstance(entries, list): continue
        valid = [e for e in entries if isinstance(e, dict) and
                 0 <= moment - _number(e.get("observed_at"), -SOURCE_TTL-1) <= SOURCE_TTL]
        if valid: out[key] = valid[-MAX_PAPER_SOURCES:]
    return out


def record(planned, state, results, observed_at):
    """Persist only bounded pages and provenance of successful logical queries."""
    state = state if isinstance(state, dict) else {}
    sources = live_sources(state, planned["signature"], observed_at)
    previous = state if state.get('pagination_signature') == planned['pagination_signature'] else {}
    old_pages = previous.get("pages") if isinstance(previous.get("pages"), dict) else {}
    pages = dict(list(old_pages.items())[-MAX_PAGE_KEYS:])
    for query, papers in results:
        page_key = query["page_key"]
        pages.pop(page_key, None)
        if query['page_mode'] == 'paged':
            pages[page_key] = query["page"] + 1 if len(papers) >= query["per_page"] and query["page"] < MAX_SOURCE_PAGE else 1
        entry = {k: query[k] for k in ("query", "kinds", "concepts", "origins", "page", "order", "page_mode", "from_date", "to_date")}
        entry["observed_at"] = observed_at
        for paper in papers[:query["per_page"]]:
            key = paper["key"]
            kept = [e for e in sources.get(key, []) if (e.get("query"), e.get("order"), e.get('page_mode')) != (query["query"], query["order"], query['page_mode'])]
            sources.pop(key, None)
            sources[key] = (kept + [entry])[-MAX_PAPER_SOURCES:]
    return {"schema_version": 2, "signature": planned["signature"], "cursors": planned["cursors"],
            "pagination_signature": planned['pagination_signature'],
            "pages": dict(list(pages.items())[-MAX_PAGE_KEYS:]),
            "sources": dict(list(sources.items())[-MAX_SOURCE_PAPERS:]),
            "last_queries": planned["queries"], "observed_at": observed_at}

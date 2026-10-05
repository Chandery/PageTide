"""The prerequisite graph behind Route Mode: validation, layers, per-branch progress, exploration share.

Pure functions on plain dicts. No network, no model, no clock, no randomness, so every result is
replayable from the same inputs (undo, freeze and pause all fall out of that).

Graph shape::

    {"concepts": [{"id", "name", "terms"[<=2], "hint"(1-4), "origin", "state", "side"}],
     "prereqs":  [{"from", "to", "support", "origin", "state"}],   # "from" is a prerequisite of "to"
     "targets":  [concept ids the reader is aiming at]}

The numbers below (0.6, 0.35, 0.1/0.4 ...) are proposals taken from the plan and from PathFinder's
0.6 mastery threshold. They have no data behind them yet; they are named constants so a replay on real
use can tune them.
"""
import copy
import math
import re

MAX_NODES = 12
MAX_FAN_IN = 3
MAX_MAP_NODES = 40     # a map may grow past the size of one AI plan, but not without limit
PRIOR = 0.1             # mastery before any evidence
START_PRIOR = 0.3       # the entry points of the map
GAIN = 0.35             # a saved paper closes this share of the remaining gap
HARD_FACTOR = 0.6       # a "too hard" paper multiplies mastery by this
SATISFIED_AT = 0.6      # a concept counts as understood from here
LOW_INTEREST_RATINGS = 3
LOW_INTEREST_AT = 0.35
EXPLORE_BASE = 0.10     # share of a batch that is exploration at the start
EXPLORE_SPAN = 0.40     # ... rising by this much as the map fills
EVENTS = ("useful", "irrelevant", "too_hard")


# ------------------------------------------------------------------ cleaning
def _text(value, limit):
    return re.sub(r"\s+", " ", re.sub(r"[,|:!\"\\\r\n\t]", " ", str(value or ""))).strip()[:limit]


def _key(text):
    return re.sub(r"[\W_]+", " ", str(text or "").lower(), flags=re.UNICODE).strip()


def _terms(raw_terms, name):
    out, seen = [], set()
    for term in raw_terms if isinstance(raw_terms, list) else []:
        cleaned = _text(term, 60)
        if cleaned and _key(cleaned) not in seen:
            seen.add(_key(cleaned))
            out.append(cleaned)
    if not out and name.isascii() and _key(name):
        out = [name.lower()]
    return out[:2]


def _hint(value):
    try:
        return max(1, min(4, int(value)))
    except (TypeError, ValueError):
        return 2


def _blank_report():
    return {"dropped_edges": [], "dropped_concepts": [], "merged": [], "terms_missing": []}


def empty_graph():
    return {"concepts": [], "prereqs": [], "targets": []}


def is_acyclic(graph):
    ids = [c["id"] for c in graph["concepts"]]
    needs = {i: [] for i in ids}
    for edge in graph["prereqs"]:
        if edge["from"] in needs and edge["to"] in needs:
            needs[edge["to"]].append(edge["from"])
    state = {}

    def visit(node):
        state[node] = 1
        for prev in needs[node]:
            if state.get(prev) == 1 or (prev not in state and not visit(prev)):
                return False
        state[node] = 2
        return True
    return all(state.get(i) == 2 or visit(i) for i in ids)


def _find_cycle(edges, order):
    """One cycle as a list of edges, or None. Deterministic: nodes are tried in `order`."""
    out = {}
    for edge in edges:
        out.setdefault(edge["from"], []).append(edge)
    color, stack = {}, []

    def visit(node):
        color[node] = 1
        for edge in sorted(out.get(node, []), key=lambda e: order.get(e["to"], 0)):
            stack.append(edge)
            if color.get(edge["to"]) == 1:
                cycle = []
                for item in reversed(stack):
                    cycle.append(item)
                    if item["from"] == edge["to"]:
                        return cycle[::-1]
            elif color.get(edge["to"]) is None:
                found = visit(edge["to"])
                if found:
                    return found
            stack.pop()
        color[node] = 2
        return None
    for node in sorted(order, key=order.get):
        if color.get(node) is None:
            found = visit(node)
            if found:
                return found
    return None


def _reachable(edges, start, goal, skip):
    out = {}
    for edge in edges:
        if edge is not skip:
            out.setdefault(edge["from"], []).append(edge["to"])
    seen, stack = set(), [start]
    while stack:
        node = stack.pop()
        if node == goal:
            return True
        if node not in seen:
            seen.add(node)
            stack.extend(out.get(node, []))
    return False


def _id_text(value):
    return str(value) if isinstance(value, (str, int)) and not isinstance(value, bool) and str(value).strip() else None


def _reduce(edges, live=None):
    """Drop every active edge that a longer active path already implies (a Hasse diagram). Only active edges
    between live concepts count as paths: a proposed or archived detour must never remove an active
    prerequisite, because progress() ignores those detours when it unlocks concepts. Returns the dropped edges."""
    def eligible(edge):
        return edge.get("state", "active") == "active" and (live is None or (edge["from"] in live and edge["to"] in live))
    dropped = []
    for edge in [e for e in edges if eligible(e)]:
        if _reachable([e for e in edges if eligible(e)], edge["from"], edge["to"], skip=edge):
            edges.remove(edge)
            dropped.append(edge)
    return dropped


def normalize(raw, max_nodes=MAX_NODES, max_fan_in=MAX_FAN_IN):
    """Make an AI-proposed (or hand-edited) concept graph safe and return (graph, report).

    Never raises on bad input. Steps: clean fields, merge duplicate concepts (same name, or identical
    terms), bound the size around the targets, drop dangling / self / duplicate edges, drop edges whose
    prerequisite is harder than the dependent, break cycles, remove shortcuts implied by longer paths, cap
    the number of prerequisites. Concepts are tracked by position, so missing or repeated ids in the input
    cannot collide; a need may refer to a concept by id or by name.
    """
    report = _blank_report()
    if not isinstance(raw, dict) or not isinstance(raw.get("concepts"), list):
        return empty_graph(), report

    # 1. clean and merge
    kept, id_map, name_map = [], {}, {}
    for position, item in enumerate(raw["concepts"]):
        if not isinstance(item, dict):
            report["dropped_concepts"].append({"name": "", "why": "not_an_object"})
            continue
        name = _text(item.get("name"), 60)
        if not name or not _key(name):
            report["dropped_concepts"].append({"name": name, "why": "no_name"})
            continue
        terms = _terms(item.get("terms"), name)
        name_key = _key(name)
        term_keys = frozenset(k for k in (_key(t) for t in terms) if k)
        needs = [str(n) for n in item["needs"] if isinstance(n, (str, int)) and not isinstance(n, bool)] if isinstance(item.get("needs"), list) else []
        user_id = _id_text(item.get("id"))
        # Same name, or the very same specific terms (a multi-word term or two terms). A single shared generic
        # word ("transformer", "learning") says nothing about two concepts being one.
        specific = len(term_keys) >= 2 or any(" " in k for k in term_keys)
        twin = next((c for c in kept if c["name_key"] == name_key or (specific and c["term_keys"] == term_keys)), None)
        if twin is not None:
            report["merged"].append({"kept": twin["name"], "dropped": name})
            twin["needs"] += needs
            if user_id and user_id not in id_map:
                id_map[user_id] = twin["pos"]
            name_map.setdefault(name_key, twin["pos"])
            continue
        record = {"pos": f"#{position}", "name": name, "terms": terms, "hint": _hint(item.get("hint")), "needs": needs,
                  "name_key": name_key, "term_keys": term_keys}
        kept.append(record)
        if user_id and user_id not in id_map:
            id_map[user_id] = record["pos"]
        name_map.setdefault(name_key, record["pos"])
        if not terms:
            report["terms_missing"].append(name)

    def resolve(ref):
        return id_map.get(str(ref)) or name_map.get(_key(ref))

    # 2. bound the size: the targets first, then their nearest ancestors (breadth first), then the rest
    raw_targets = list(dict.fromkeys(t for t in (resolve(x) for x in raw.get("targets") if isinstance(x, (str, int)) and not isinstance(x, bool)) if t)) \
        if isinstance(raw.get("targets"), list) else []
    needs_of = {c["pos"]: [r for r in (resolve(n) for n in c["needs"]) if r] for c in kept}
    priority, queue = [], list(raw_targets)
    while queue:
        node = queue.pop(0)
        if node not in priority:
            priority.append(node)
            queue.extend(needs_of.get(node, []))
    ranked = priority + [c["pos"] for c in kept if c["pos"] not in priority]
    keep_ids = set(ranked[:max_nodes])
    for c in kept:
        if c["pos"] not in keep_ids:
            report["dropped_concepts"].append({"name": c["name"], "why": "too_many"})
    kept = [c for c in kept if c["pos"] in keep_ids]

    # 3. canonical ids
    new_id = {c["pos"]: f"c{i + 1}" for i, c in enumerate(kept)}
    position = {new_id[c["pos"]]: i for i, c in enumerate(kept)}
    hints = {new_id[c["pos"]]: c["hint"] for c in kept}
    name_of = {new_id[c["pos"]]: c["name"] for c in kept}

    # 4. edges
    edges, seen = [], set()
    for c in kept:
        for need in c["needs"]:
            source = resolve(need)
            pair = (new_id.get(source), new_id[c["pos"]])

            def drop(why):
                report["dropped_edges"].append({"from": name_of.get(pair[0], str(need)), "to": name_of[pair[1]], "why": why})
            if source is None or pair[0] is None:
                drop("dangling")
            elif pair[0] == pair[1]:
                drop("self")
            elif pair in seen:
                continue
            elif hints[pair[0]] > hints[pair[1]]:
                seen.add(pair)
                drop("hint_order")
            else:
                seen.add(pair)
                edges.append({"from": pair[0], "to": pair[1], "support": None, "origin": "plan", "state": "active"})

    # 5. cycles: remove the edge whose prerequisite is hardest, then the latest, until none is left
    while True:
        cycle = _find_cycle(edges, position)
        if not cycle:
            break
        victim = max(cycle, key=lambda e: (hints[e["from"]], position[e["from"]], position[e["to"]]))
        edges.remove(victim)
        report["dropped_edges"].append({"from": name_of[victim["from"]], "to": name_of[victim["to"]], "why": "cycle"})

    # 6. shortcuts implied by a longer path
    for edge in list(edges):
        if _reachable(edges, edge["from"], edge["to"], skip=edge):
            edges.remove(edge)
            report["dropped_edges"].append({"from": name_of[edge["from"]], "to": name_of[edge["to"]], "why": "redundant"})

    # 7. cap the prerequisites of one concept (keep the first ones in the order they were proposed)
    for target in sorted({e["to"] for e in edges}, key=position.get):
        incoming = [e for e in edges if e["to"] == target]
        for edge in incoming[max_fan_in:]:
            edges.remove(edge)
            report["dropped_edges"].append({"from": name_of[edge["from"]], "to": name_of[edge["to"]], "why": "fan_in"})

    concepts = [{"id": new_id[c["pos"]], "name": c["name"], "terms": c["terms"], "hint": c["hint"],
                 "origin": "plan", "state": "active", "side": False} for c in kept]
    targets = [new_id[t] for t in raw_targets if t in new_id]
    graph = {"concepts": concepts, "prereqs": edges, "targets": targets}
    if not targets:
        graph["targets"] = [c["id"] for c in concepts if not any(e["from"] == c["id"] for e in edges)]
    reach = ancestors(graph, graph["targets"]) | set(graph["targets"])
    for c in graph["concepts"]:
        c["side"] = c["id"] not in reach
    return graph, report


# ----------------------------------------------------------------- structure
def layers(graph):
    """Topological level of every concept: 1 for entry points, 1 + the deepest prerequisite otherwise."""
    needs = {c["id"]: [] for c in graph["concepts"]}
    for edge in graph["prereqs"]:
        if edge["from"] in needs and edge["to"] in needs:
            needs[edge["to"]].append(edge["from"])
    memo = {}

    def depth(node, trail=()):
        if node in memo:
            return memo[node]
        if node in trail:
            return 1   # a cycle should not exist; never recurse forever on one
        memo[node] = 1 + max((depth(p, trail + (node,)) for p in needs[node]), default=0)
        return memo[node]
    return {c["id"]: depth(c["id"]) for c in graph["concepts"]}


def ancestors(graph, ids):
    needs = {}
    for edge in graph["prereqs"]:
        needs.setdefault(edge["to"], []).append(edge["from"])
    found, stack = set(), list(ids)
    while stack:
        for prev in needs.get(stack.pop(), []):
            if prev not in found:
                found.add(prev)
                stack.append(prev)
    return found


def descendants(graph, ids):
    after = {}
    for edge in graph["prereqs"]:
        after.setdefault(edge["from"], []).append(edge["to"])
    found, stack = set(), list(ids)
    while stack:
        for nxt in after.get(stack.pop(), []):
            if nxt not in found:
                found.add(nxt)
                stack.append(nxt)
    return found


def _next_id(graph):
    numbers = [int(c["id"][1:]) for c in graph["concepts"] if re.fullmatch(r"c\d+", c["id"])]
    return f"c{max(numbers, default=0) + 1}"


def add_concept(graph, concept, needs=(), dependents=()):
    """A copy of the graph with one more concept. `needs` are its prerequisites, `dependents` the concepts
    that will require it. Applies the same rules as normalize(): raises ValueError for unknown ids, a missing
    name, a prerequisite that is harder than its dependent, more than MAX_FAN_IN prerequisites for any concept,
    a cycle, or a map past MAX_MAP_NODES. Edges implied by a longer path are dropped, so the result stays a
    reduced graph (adding X between A and B replaces A -> B with A -> X -> B)."""
    needs, dependents = list(dict.fromkeys(needs)), list(dict.fromkeys(dependents))
    hints = {c["id"]: c["hint"] for c in graph["concepts"]}
    if any(i not in hints for i in needs + dependents):
        raise ValueError("unknown concept")
    name = _text(concept.get("name"), 60)
    if not name or not _key(name):
        raise ValueError("a concept needs a name")
    if len(graph["concepts"]) >= MAX_MAP_NODES:
        raise ValueError("the map is full")
    hint = _hint(concept.get("hint"))
    if any(hints[i] > hint for i in needs) or any(hint > hints[i] for i in dependents):
        raise ValueError("a prerequisite cannot be harder than the concept that needs it")
    grown = copy.deepcopy(graph)
    new_id = _next_id(graph)
    origin, state = concept.get("origin", "user"), concept.get("state", "active")
    grown["concepts"].append({"id": new_id, "name": name, "terms": _terms(concept.get("terms"), name), "hint": hint,
                              "origin": origin, "state": state, "side": False})
    for source in needs:
        grown["prereqs"].append({"from": source, "to": new_id, "support": concept.get("support"), "origin": origin, "state": state})
    for target in dependents:
        grown["prereqs"].append({"from": new_id, "to": target, "support": None, "origin": origin, "state": state})
    if not is_acyclic(grown):
        raise ValueError("that would make a cycle")
    _reduce(grown["prereqs"], live={c["id"] for c in grown["concepts"] if c.get("state", "active") == "active"})
    for node in [new_id] + dependents:
        if sum(1 for e in grown["prereqs"] if e["to"] == node) > MAX_FAN_IN:
            raise ValueError("too many prerequisites for one concept")
    return grown


_CONCEPT_EXTRAS = ("parent", "evidence", "candidate", "direction_id")
_ORIGINS, _STATES = ("plan", "user", "grown"), ("active", "proposed", "archived")


def _short(value, name):
    if not isinstance(value, str) or len(value) > 200:
        raise ValueError(f"{name} must be a short string")
    return value


def validate(graph):
    """A clean deep copy of a structured graph, or ValueError naming the broken rule.

    This is the gate for graphs that were not just made by normalize(): a graph a person edited on the page or
    one grown by merge_candidate(). Rules: unique string ids, a name on every concept, at least one active
    concept, edges between known concepts with no self edge or duplicate, no cycle, no prerequisite harder than
    its dependent, at most MAX_FAN_IN prerequisites, at most MAX_MAP_NODES concepts, targets that exist (the
    sinks when none are given), bounded extra fields. Active edges implied by a longer active path are dropped
    quietly (reachability is unchanged). Unknown fields are dropped.
    """
    try:
        return _validate(graph)
    except (TypeError, AttributeError, KeyError) as exc:
        raise ValueError("not a valid map") from exc


def _validate(graph):
    if not isinstance(graph, dict) or not isinstance(graph.get("concepts"), list) or not isinstance(graph.get("prereqs"), list):
        raise ValueError("not a map")
    if len(graph["concepts"]) > MAX_MAP_NODES or len(graph["prereqs"]) > MAX_MAP_NODES * MAX_FAN_IN:
        raise ValueError("the map is too big")
    concepts, ids = [], set()
    for item in graph["concepts"]:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"] or item["id"] in ids:
            raise ValueError("every concept needs its own id")
        _short(item["id"], "id")
        name = _text(item.get("name"), 60)
        if not name or not _key(name):
            raise ValueError("a concept needs a name")
        origin, state = item.get("origin", "plan"), item.get("state", "active")
        if origin not in _ORIGINS or state not in _STATES:
            raise ValueError("unknown origin or state")
        ids.add(item["id"])
        clean = {"id": item["id"], "name": name, "terms": _terms(item.get("terms"), name), "hint": _hint(item.get("hint")),
                 "origin": origin, "state": state, "side": False}
        for extra in ("parent", "candidate", "direction_id"):
            if item.get(extra) is not None:
                clean[extra] = _short(item[extra], extra)
        if item.get("evidence") is not None:
            evidence = item["evidence"]
            if not isinstance(evidence, list) or len(evidence) > 12:
                raise ValueError("evidence must be a short list")
            clean["evidence"] = [_short(e, "evidence") for e in evidence]
        concepts.append(clean)
    if not any(c["state"] == "active" for c in concepts):
        raise ValueError("The map has no active concepts")
    hints = {c["id"]: c["hint"] for c in concepts}
    edges, seen = [], set()
    for item in graph["prereqs"]:
        if not isinstance(item, dict) or not isinstance(item.get("from"), str) or not isinstance(item.get("to"), str) \
                or item["from"] not in ids or item["to"] not in ids:
            raise ValueError("an edge joins unknown concepts")
        pair = (item["from"], item["to"])
        if pair[0] == pair[1] or pair in seen:
            raise ValueError("an edge points at itself or is repeated")
        if hints[pair[0]] > hints[pair[1]]:
            raise ValueError("a prerequisite cannot be harder than the concept that needs it")
        origin, state = item.get("origin", "plan"), item.get("state", "active")
        if origin not in _ORIGINS or state not in ("active", "proposed"):
            raise ValueError("unknown origin or state")
        support = item.get("support")
        seen.add(pair)
        edges.append({"from": pair[0], "to": pair[1],
                      "support": support if isinstance(support, (int, float)) and not isinstance(support, bool) and math.isfinite(support) else None,
                      "origin": origin, "state": state})
    targets = graph.get("targets", [])
    if not isinstance(targets, list) or any(not isinstance(t, str) or t not in ids for t in targets):
        raise ValueError("a target is not on the map")
    clean_graph = {"concepts": concepts, "prereqs": edges, "targets": list(dict.fromkeys(targets))}
    if not is_acyclic(clean_graph):
        raise ValueError("that would make a cycle")
    _reduce(edges, live={c["id"] for c in concepts if c["state"] == "active"})
    for node in ids:
        if sum(1 for e in edges if e["to"] == node) > MAX_FAN_IN:
            raise ValueError("too many prerequisites for one concept")
    if not clean_graph["targets"]:
        feeding = {e["from"] for e in edges}
        clean_graph["targets"] = [c["id"] for c in concepts if c["state"] == "active" and c["id"] not in feeding]
    reach = ancestors(clean_graph, clean_graph["targets"]) | set(clean_graph["targets"])
    for c in concepts:
        c["side"] = c["id"] not in reach
    return clean_graph


def remove_concept(graph, concept_id):
    smaller = copy.deepcopy(graph)
    smaller["concepts"] = [c for c in smaller["concepts"] if c["id"] != concept_id]
    smaller["prereqs"] = [e for e in smaller["prereqs"] if concept_id not in (e["from"], e["to"])]
    smaller["targets"] = [t for t in smaller["targets"] if t != concept_id]
    return smaller


# ------------------------------------------------------------------ progress
def progress(graph, events, manual=None, shown=None, start=None):
    """Per-concept state from explicit feedback only.

    events: {concept_id: ["useful" | "irrelevant" | "too_hard", ...]} in the order they happened.
    manual: {concept_id: "mastered" | "unlocked" | "demoted"}.   shown: {concept_id: papers shown}.
    start: the entry points; the roots when omitted.

    Mastery m (what unlocks the next concepts): starts at PRIOR (START_PRIOR for entry points), a saved
    paper moves it toward 1, a "too hard" paper scales it down, nothing else touches it. Interest p comes
    from ratings alone: (saved + 1) / (rated + 2). Silence, "irrelevant" and unmet prerequisites never lower
    mastery, and no concept is ever marked as disliked.

    Only active concepts and active edges take part in unlocking. A proposed concept (an unconfirmed
    suggestion) has status "proposed" and an archived one "archived"; neither is on the frontier and neither
    blocks the concepts after it. A manually mastered concept is satisfied even when its own prerequisites are
    not (the reader says they know it); its `unmet` list still shows them. A cycle in stored data cannot crash
    this: its members stay locked until the reader breaks the cycle.
    """
    events, manual, shown = events or {}, manual or {}, shown or {}
    ids = [c["id"] for c in graph["concepts"]]
    state_of = {c["id"]: c.get("state", "active") for c in graph["concepts"]}
    index = {i: n for n, i in enumerate(ids)}
    needs = {i: [] for i in ids}
    for edge in graph["prereqs"]:
        if (edge["from"] in needs and edge["to"] in needs and edge.get("state", "active") == "active"
                and state_of[edge["from"]] == "active" and state_of[edge["to"]] == "active"):
            needs[edge["to"]].append(edge["from"])
    level = layers(graph)
    starts = set(start) if start is not None else {i for i in ids if not needs[i]}
    out = {}
    for node in sorted(ids, key=lambda i: (level[i], index[i])):
        counts = {name: 0 for name in EVENTS}
        mastery = START_PRIOR if node in starts else PRIOR
        for name in events.get(node, []):
            if name not in counts:
                continue
            counts[name] += 1
            if name == "useful":
                mastery += (1 - mastery) * GAIN
            elif name == "too_hard":
                mastery *= HARD_FACTOR
        rated = counts["useful"] + counts["irrelevant"]
        interest = (counts["useful"] + 1) / (rated + 2)
        override = manual.get(node)
        satisfied = override == "mastered" or mastery >= SATISFIED_AT
        unmet = sorted((p for p in needs[node] if out.get(p, {}).get("status") != "satisfied"), key=lambda p: (level[p], index[p]))
        if state_of[node] != "active":
            status = state_of[node]
        elif satisfied:
            status = "satisfied"
        elif not unmet or override == "unlocked":
            status = "unlocked"
        else:
            status = "locked"
        out[node] = {"m": mastery, "useful": counts["useful"], "irrelevant": counts["irrelevant"], "too_hard": counts["too_hard"],
                     "rated": rated, "shown": int(shown.get(node, 0)), "p": interest,
                     "low_interest": override == "demoted" or (rated >= LOW_INTEREST_RATINGS and interest <= LOW_INTEREST_AT),
                     "status": status, "manual": override, "unmet": unmet}
    return out


def frontier(graph, prog):
    """Concepts to read from now: unlocked and not yet understood, nearest to the basics first, then by interest."""
    level = layers(graph)
    order = {c["id"]: i for i, c in enumerate(graph["concepts"])}
    open_ids = [i for i, state in prog.items() if state["status"] == "unlocked"]
    return sorted(open_ids, key=lambda i: (level[i], -prog[i]["p"], order[i]))


def remedial(graph, prog, concept_id):
    """The unmet prerequisites to read first when a concept proved too hard, most basic first."""
    return list(prog.get(concept_id, {}).get("unmet", []))


# --------------------------------------------------------------- exploration
def exploration_share(done, total):
    """Share of a batch spent outside the unlocked frontier: EXPLORE_BASE at the start, rising to
    EXPLORE_BASE + EXPLORE_SPAN as the share of understood concepts goes to 1. A smooth curve, not a switch."""
    ratio = 0.0 if total <= 0 else max(0.0, min(1.0, done / total))
    return EXPLORE_BASE + EXPLORE_SPAN * ratio


def exploration_slots(batch_size, done, total, batch_index):
    """Exploration slots in batch number `batch_index` (0-based). Cumulative rounding, so the average
    over batches equals the share exactly and the same batch number always gives the same answer.
    At least one slot of every batch stays on the route."""
    if batch_size <= 1:
        return 0   # a one-paper batch has no room for exploration; the average-equals-share claim holds from two papers
    batch_index = max(0, int(batch_index))
    share = exploration_share(done, total) * batch_size
    slots = int(math.floor(share * (batch_index + 1) + 1e-9) - math.floor(share * batch_index + 1e-9))
    return max(0, min(slots, batch_size - 1))


def allocate(slots, weights):
    """Split `slots` among items in proportion to `weights` (largest remainder; ties go to the earlier item)."""
    weights = [w if isinstance(w, (int, float)) and not isinstance(w, bool) and math.isfinite(w) and w > 0 else 0 for w in weights]
    total = sum(weights)
    if slots <= 0 or total <= 0:
        return [0] * len(weights)
    quotas = [slots * w / total for w in weights]
    shares = [int(q) for q in quotas]
    leftovers = sorted(range(len(weights)), key=lambda i: (-(quotas[i] - shares[i]), i))
    for i in leftovers[:slots - sum(shares)]:
        shares[i] += 1
    return shares

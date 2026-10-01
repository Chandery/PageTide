"""Profile-led, fine-grained category suggestions; offline, deterministic, zero model tokens.

Top-level groups come from the current project's pinned profile terms: what the
owner said they want to read. A pinned term whose papers almost all belong to a
wider pinned term is nested under it. Inside each group, and among papers no
pinned term covers, sub-groups are phrases repeated in two or more paper titles.

OpenAlex topics are deliberately unused: they are coarse discipline labels and
split one research line (e.g. world models) into robotics / multimodal / GAN
groups. Every group names the phrase it rests on. The glossary only names a
phrase; unknown phrases keep their original wording instead of a guessed label.
"""
import hashlib
import json
import re
from collections import Counter, defaultdict

from .clustering import MAX_PAPERS, MAX_TEXT, corpus_fingerprint, _corpus
from .organization_terms import LABELS

ALGORITHM = "profile-facets-v1"
MIN_GROUP = 2
MAX_TOP = 12
MAX_CHILDREN = 6
NEST = .8          # share of a pinned term's papers that must sit inside a wider one
DUPLICATE = .8     # Jaccard above which two candidate groups are the same group
MAX_TERMS = 40
DEFAULT_COLOR = "#64748b"

# Words that cannot start or end a phrase, and bare words never offered alone.
FUNCTION = set("""a an the of for with via from to in on and or as by at into onto towards toward
using use can do does is are be we our its their beyond without under through across over
vs versus not no all any new""".split())
WEAK = set("""model learn method approach framework system network study analysis toward
towards task data dataset benchmark result novel efficient effective robust scalable simple
general unified large small real time based driven aware free end level""".split())
CJK = re.compile(r"[㐀-鿿]")
# Clause punctuation: a phrase never spans "real world. Model predictive ...".
# A period followed by a letter or digit is part of a name ("Qwen2.5", "Llama 3.1"), not a break.
CLAUSE = re.compile(r"\.(?![^\W_])|[,;:!?()\[\]{}\"“”，。；：！？（）、]")


def stem(word):
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 5 and word.endswith("ing"):
        word = word[:-3]
        return word[:-1] if len(word) > 3 and word[-1] == word[-2] and word[-1] not in "aeious" else word
    if len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    return word


def words(text):
    """Latin/digit words with original spelling, split on hyphens and punctuation."""
    return [w for w in re.findall(r"[^\W_]+", text or "", re.UNICODE) if not CJK.search(w)]


def _stems(text):
    return [stem(w.lower()) for w in words(text)]


def _segments(text):
    """Stem lists per clause; matching never crosses clause punctuation."""
    return [stems for stems in (_stems(part) for part in CLAUSE.split(text or "")) if stems]


def _contains(doc, term, gap=1):
    """Ordered term stems inside one clause of doc, at most `gap` extra words between neighbours."""
    if not term:
        return False
    for segment in doc:
        for start, token in enumerate(segment):
            if token != term[0]:
                continue
            position, ok = start, True
            for part in term[1:]:
                window = segment[position + 1:position + 2 + gap]
                if part not in window:
                    ok = False
                    break
                position += 1 + window.index(part)
            if ok:
                return True
    return False


def _label(phrase_stems):
    for english, label in LABELS.items():
        if _stems(english) == phrase_stems:
            return label
    return None


def _variants(term):
    """Stem sequences for a pinned term; Chinese glossary names map back to English.

    A term with Chinese characters is never reduced to its Latin words ("LLM 推理"
    is not "LLM"): it matches its exact text, or the English of an exact glossary name.
    """
    stems = _stems(term)
    variants = [stems] if stems and not CJK.search(term) else []
    for english, label in LABELS.items():
        if label == term.strip() and _stems(english) not in variants:
            variants.append(_stems(english))
    return variants


def _jaccard(a, b):
    return len(a & b) / len(a | b) if a | b else 0


def _clean_terms(values):
    if values is None:
        return []
    if not isinstance(values, list) or len(values) > MAX_TERMS:
        raise ValueError("profile terms must be an array of at most %d strings" % MAX_TERMS)
    terms = []
    for value in values:
        if not isinstance(value, str) or len(value) > 100:
            raise ValueError("profile terms must be strings of at most 100 characters")
        value = " ".join(value.split())
        if value and value.lower() not in {t.lower() for t in terms}:
            terms.append(value)
    return terms


def _phrases(rows, keys, exclude):
    """Title phrases shared by >= MIN_GROUP of `keys`: {stems: (docs, surface)}."""
    surfaces, titles, index = defaultdict(Counter), {}, defaultdict(set)
    for key in keys:
        titles[key] = [_count_grams(original, exclude, surfaces)
                       for original in map(words, CLAUSE.split(rows[key]["title"])) if original]
        for segment in titles[key]:
            for token in segment:
                index[token].add(key)
    # Membership tolerates one inserted word, as for pinned terms: "World Action
    # Model" belongs to "world model" too. Only titles holding the first stem are checked.
    found = {}
    for gram, forms in surfaces.items():
        members = {key for key in index[gram[0]] if _contains(titles[key], gram)}
        if len(members) >= MIN_GROUP:
            found[gram] = (members, sorted(forms, key=lambda s: (-forms[s], s))[0])
    return found


def _count_grams(original, exclude, surfaces):
    """Count the 1-3 word phrases of one title clause into `surfaces`; return its stems."""
    stems = [stem(w.lower()) for w in original]
    for size in (1, 2, 3):
        for i in range(len(stems) - size + 1):
            gram = tuple(stems[i:i + size])
            surface = original[i:i + size]
            if gram[0] in FUNCTION or gram[-1] in FUNCTION or any(s.isdigit() for s in gram):
                continue
            if size == 1:
                # A bare word only stands alone as an acronym or a glossary term.
                word = surface[0]
                if gram[0] in WEAK or not ((word.isupper() and len(word) >= 3) or _label(list(gram))):
                    continue
            elif gram[0] in WEAK and gram[-1] in WEAK:
                continue
            if any(set(gram) <= set(ex) for ex in exclude):
                continue
            surfaces[gram][" ".join(surface)] += 1
    return stems


def _pick(candidates, universe, limit, interest):
    """Greedy cover: prefer phrases that are longer, add unseen papers and echo interest words."""
    chosen, covered = [], set()
    pool = dict(candidates)
    while pool and len(chosen) < limit:
        def score(item):
            gram, (members, _) = item
            new = len(members - covered)
            bonus = 1 if set(gram) & interest else 0
            return (new * (1 + .5 * (len(gram) - 1)) + bonus, len(members), len(gram), gram)
        gram, (members, surface) = max(pool.items(), key=score)
        del pool[gram]
        if not members - covered or len(members) >= len(universe):
            continue
        if any(_jaccard(members, other) >= DUPLICATE for _, other, _ in chosen):
            continue
        chosen.append((gram, members, surface))
        covered |= members
    return chosen


def _group(kind, basis, keys, parent, name, reason, terms):
    digest = hashlib.sha256(json.dumps([parent, kind, basis, sorted(keys)],
                                       ensure_ascii=True).encode()).hexdigest()[:20]
    return {"id": "facet-" + digest, "name": name, "keys": sorted(keys), "parent": parent,
            "source": kind, "terms": terms, "reason": reason, "color": DEFAULT_COLOR}


# Suggestion reasons in the interface language (profile["language"], set by the server).
REASONS = {
    "zh-CN": {"nested": "固定关键词「%s」的论文大多也属于「%s」，放在其下",
              "phrase": "「%s」中 %d 篇标题都出现 “%s”%s", "echo": "；含画像兴趣词 ", "sep": "、",
              "pinned": "来自画像固定关键词「%s」：标题或摘要提到它的论文",
              "rest": "不含画像固定关键词；%d 篇标题都出现 “%s”",
              "rest_unpinned": "当前项目还没有固定关键词；%d 篇标题都出现 “%s”"},
    "en-US": {"nested": "Most papers with the pinned keyword “%s” also belong to “%s”, so it sits under it",
              "phrase": "In “%s”, %d titles contain “%s”%s", "echo": "; includes profile interest words ", "sep": ", ",
              "pinned": "From the pinned profile keyword “%s”: papers whose title or abstract mention it",
              "rest": "No pinned profile keyword; %d titles contain “%s”",
              "rest_unpinned": "This project has no pinned keywords yet; %d titles contain “%s”"},
}


def _phrase_name(gram, surface):
    label = _label(list(gram))
    return label or surface


def suggest_groups(papers, profile=None):
    """Preview groups for saved papers.

    profile: {"pinned": [str], "interest": [str], "project": str}; pinned terms
    become categories, interest words only break ties between title phrases.
    Returns the stored preview shape used by Organization.
    """
    rows_list = _corpus(papers)
    if len(rows_list) > MAX_PAPERS:
        raise ValueError("Suggestions support at most %d saved papers" % MAX_PAPERS)
    if any(sum(len(row[f]) for f in ("title", "abstract", "topic")) > MAX_TEXT for row in rows_list):
        raise ValueError("Paper text exceeds suggestion limit")
    profile = profile or {}
    if not isinstance(profile, dict):
        raise ValueError("profile must be an object")
    english = profile.get("language") == "en-US"
    text_of = REASONS["en-US" if english else "zh-CN"]
    # The glossary gives Chinese display names; an English interface keeps the paper's wording.
    display = (lambda term: term) if english else (lambda term: LABELS.get(term.lower(), term))
    phrase_name = (lambda gram, surface: surface) if english else _phrase_name
    pinned = _clean_terms(profile.get("pinned"))
    interest = {stem(t.lower()) for t in _clean_terms(profile.get("interest")) if not CJK.search(t)}
    rows = {row["key"]: row for row in rows_list}
    keys = sorted(rows)
    text = {key: rows[key]["title"] + " " + rows[key]["abstract"] for key in keys}
    doc = {key: _segments(rows[key]["title"]) + _segments(rows[key]["abstract"]) for key in keys}

    # 1. Pinned profile terms: title or abstract mentions the term.
    matched, unmatched = [], []
    for order, term in enumerate(pinned):
        variants = _variants(term)
        members = {key for key in keys
                   if any(_contains(doc[key], v) for v in variants)
                   or (CJK.search(term) and term.lower() in text[key].lower())}
        if len(members) >= MIN_GROUP:
            matched.append({"term": term, "keys": members, "order": order, "variants": variants})
        else:
            unmatched.append({"term": term, "documents": len(members)})
    matched.sort(key=lambda m: (-len(m["keys"]), m["order"]))
    tops, children = [], defaultdict(list)
    for entry in matched:
        if any(_jaccard(entry["keys"], top["keys"]) >= DUPLICATE for top in tops):
            unmatched.append({"term": entry["term"], "documents": len(entry["keys"]),
                              "same_as": next(t["term"] for t in tops
                                              if _jaccard(entry["keys"], t["keys"]) >= DUPLICATE)})
            continue
        parent = next((top for top in tops if len(top["keys"]) > len(entry["keys"])
                       and len(entry["keys"] & top["keys"]) >= NEST * len(entry["keys"])), None)
        if parent:
            children[parent["term"]].append(entry)
        else:
            tops.append(entry)
    for top in tops[MAX_TOP:]:
        # Over the category limit: say so instead of silently dropping the term.
        for entry in [top] + children.pop(top["term"], []):
            unmatched.append({"term": entry["term"], "documents": len(entry["keys"]), "dropped": True})
    tops = tops[:MAX_TOP]

    groups = []

    def add_children(parent_group, members, exclude, reserved):
        taken = [set(child["keys"]) & members for child in reserved]
        for child in reserved:
            share = set(child["keys"]) & members
            groups.append(_group("pinned", child["term"], share, parent_group["id"],
                                 display(child["term"]),
                                 text_of["nested"] % (child["term"], parent_group["name"]),
                                 [child["term"]]))
        candidates = {gram: value for gram, value in _phrases(rows, members, exclude).items()
                      if len(value[0]) < len(members)
                      and not any(_jaccard(value[0], t) >= DUPLICATE for t in taken)}
        for gram, share, surface in _pick(candidates, members, MAX_CHILDREN - len(reserved), interest):
            # Only name interest words the parent does not already say.
            echo = sorted(set(gram) & interest - WEAK - {s for ex in exclude for s in ex})
            groups.append(_group("phrase", " ".join(gram), share, parent_group["id"],
                                 phrase_name(gram, surface),
                                 text_of["phrase"] % (
                                     parent_group["name"], len(share), surface,
                                     text_of["echo"] + text_of["sep"].join(echo) if echo else ""),
                                 [surface]))

    for top in tops:
        group = _group("pinned", top["term"], top["keys"], None,
                       display(top["term"]), text_of["pinned"] % top["term"], [top["term"]])
        groups.append(group)
        own = [tuple(v) for v in top["variants"]] + [tuple(_stems(top["term"]))]
        add_children(group, top["keys"], [ex for ex in own if ex], children[top["term"]])

    # 2. Papers no pinned term covers: repeated title phrases, never discipline labels.
    covered = set().union(*(top["keys"] for top in tops)) if tops else set()
    rest = [key for key in keys if key not in covered]
    phrase_tops = _pick(_phrases(rows, rest, []), rest + ["\0"], MAX_TOP - len(tops), interest) if len(rest) >= MIN_GROUP else []
    for gram, members, surface in phrase_tops:
        reason = text_of["rest" if pinned else "rest_unpinned"] % (len(members), surface)
        group = _group("phrase", " ".join(gram), members, None, phrase_name(gram, surface), reason, [surface])
        groups.append(group)
        if len(members) >= 2 * MIN_GROUP:
            add_children(group, members, [gram], [])
    placed = {key for group in groups for key in group["keys"]}
    return {"fingerprint": corpus_fingerprint(rows_list), "algorithm": ALGORITHM,
            "groups": groups, "pending_keys": [key for key in keys if key not in placed],
            "profile": {"project": profile.get("project") if isinstance(profile.get("project"), str) else None,
                        "pinned": pinned, "unmatched": unmatched}}

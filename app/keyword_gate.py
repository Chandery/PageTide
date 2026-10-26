"""A paper belongs to a project only when it mentions one of the project's own terms (owner, 2026-10-26).

The terms are the project's keywords (the pinned profile terms) and, when the project has a learning map, the search terms
of its concepts. A paper whose title, abstract or own keywords mention none of them is not stored by a fetch and never
recommended: a Chinese keyword sent to OpenAlex's relevance search matched single characters, and 70-100% of what Chinese
projects fetched mentioned no keyword at all (measured on the owner's libraries, 2026-10-26).

Matching is local, exact and explainable; no model, no synonyms:
- a term with Chinese characters matches as one unbroken phrase (spaces ignored on both sides), so 语法教学 needs 语法教学;
- an English term matches when every content word appears as a word, in any common form (model / models / modelling);
- a project with no terms at all is not gated (nothing to compare with).
English papers in a project with only Chinese terms therefore never match (owner's choice: no keyword, no paper).
"""
import re
import unicodedata

_CJK = re.compile(r"[㐀-鿿豈-﫿]")
_WORD = re.compile(r"[a-z0-9]+")
_STOP = {"a", "an", "the", "of", "for", "and", "or", "in", "on", "to", "with", "by", "via", "from", "at", "as", "is", "are"}
_SUFFIX = re.compile(r"(?:ies|es|s|ing|ed|er|ers|ation|ations|al|ally|ly)$")


def _fold(text):
    return unicodedata.normalize("NFKC", str(text or "")).casefold()


def _stem(word):
    if len(word) <= 4 or word.isdigit():
        return word
    if word.endswith("sis"):                       # analysis / analyses, hypothesis / hypotheses
        return word[:-2]
    stem = _SUFFIX.sub("", word)
    if len(stem) > 4 and stem[-1] == stem[-2]:     # modelling -> model, labelled -> label
        stem = stem[:-1]
    return stem if len(stem) >= 4 else word[:4]


def _english_pattern(term):
    words = [w for w in _WORD.findall(term) if w not in _STOP]
    if not words:
        return None
    return [re.compile(r"\b" + re.escape(_stem(w)) + r"[a-z]*\b") if not w.isdigit() else re.compile(r"\b" + w + r"\b")
            for w in words]


class Gate:
    """Built once per project and check; `matches(paper)` says whether the paper mentions any term."""

    def __init__(self, terms):
        self.phrases, self.patterns = [], []
        for term in terms or ():
            folded = _fold(term).strip()
            if not folded:
                continue
            if _CJK.search(folded):
                self.phrases.append(re.sub(r"\s+", "", folded))
            else:
                pattern = _english_pattern(folded)
                if pattern:
                    self.patterns.append(pattern)

    @property
    def active(self):
        return bool(self.phrases or self.patterns)

    def matches(self, paper):
        if not self.active:
            return True
        text = _fold(" ".join(str(paper.get(field) or "") for field in ("title", "abstract")))
        if str(paper.get("key") or "").startswith("cnki:"):
            text += " " + _fold(paper.get("topic"))        # 知网's own first keyword; an OpenAlex topic is a classification, not used
            text += " " + " ".join(_fold(k) for k in paper.get("keywords") or () if isinstance(k, str))
        squeezed = re.sub(r"\s+", "", text)
        if any(phrase in squeezed for phrase in self.phrases):
            return True
        return any(all(p.search(text) for p in pattern) for pattern in self.patterns)

    def keep(self, papers):
        """(kept, dropped count)."""
        kept = [p for p in papers if self.matches(p)]
        return kept, len(papers) - len(kept)


def route_terms(route):
    """The search terms of a learning map's concepts (route block as stored), or none."""
    graph = (route or {}).get("graph") or route or {}
    terms = []
    for concept in graph.get("concepts") or ():
        if isinstance(concept, dict):
            terms += [t for t in concept.get("terms") or () if isinstance(t, str)]
            if isinstance(concept.get("name"), str):
                terms.append(concept["name"])
    return terms

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

_CJK = re.compile(r"[㐀-鿿豈-﫿]")
_WORD = re.compile(r"[a-z0-9]+")
_STOP = {"a", "an", "the", "of", "for", "and", "or", "in", "on", "to", "with", "by", "via", "from", "at", "as", "is", "are"}
# The endings a word may take and still be the same word. A fixed list, never "any letters": a bare prefix let "art" match
# "article" and "basis" match "based" (independent review, 2026-10-26).
_ENDINGS = r"(?:s|es|ed|ing|er|ers|al|ally|ly|ation|ations)?"
_STRIP = re.compile(r"(?:ations|ation|ally|ings|ing|ers|er|ed|es|s|al|ly)$")


def _fold(text):
    return unicodedata.normalize("NFKC", str(text or "")).casefold()


def _word_pattern(word):
    """One word in any common form. Boundaries are "no letter or digit next to it", not \\b: a Chinese character counts
    as a word character for \\b, so "基于Transformer的" would not match "transformer"."""
    if word.isdigit() or len(word) <= 3:
        body = re.escape(word) + (r"(?:s|es)?" if not word.isdigit() else "")
    elif word.endswith("sis") and len(word) >= 8:            # analysis / analyses, hypothesis / hypotheses
        body = re.escape(word[:-2]) + r"(?:is|es)"
    elif re.search(r"[^aeiou]y$", word):                     # study / studies / studied
        body = re.escape(word[:-1]) + r"(?:y|ies|ied)"
    elif word.endswith("ies") and len(word) > 5:             # studies -> study
        body = re.escape(word[:-3]) + r"(?:y|ies|ied)"
    else:
        stem = _STRIP.sub("", word) if len(word) > 5 else word
        if len(stem) < 4:
            stem = word
        if len(stem) > 4 and stem[-1] == stem[-2] and stem[-1] not in "aeiou":
            stem = stem[:-1]                                 # modelling -> model, labelled -> label
        double = re.escape(stem[-1]) + "?" if stem[-1] not in "aeiou" else ""
        body = re.escape(stem) + r"(?:e)?" + double + _ENDINGS   # model, models, modelling; compute, computation
    return re.compile(r"(?<![a-z0-9])" + body + r"(?![a-z0-9])")


def _english_pattern(term):
    words = [w for w in _WORD.findall(term) if w not in _STOP]
    return [_word_pattern(w) for w in words] or None


class Gate:
    """Built once per project and check; `matches(paper)` says whether the paper mentions any term."""

    def __init__(self, terms):
        self.phrases, self.patterns = [], []
        for term in terms or ():
            folded = _fold(term).strip()
            if not folded:
                continue
            if _CJK.search(folded):
                # Every part of a spaced term must appear, as the OpenAlex query asks (汉语 语法: both, anywhere).
                parts = []
                for part in folded.split():
                    if _CJK.search(part):
                        parts.append(part)                        # a Chinese part: a substring, spaces ignored
                    else:
                        parts += _english_pattern(part) or []     # an English part (Si, CVD): whole words
                self.phrases.append(parts)
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
        if any(parts and all(part in squeezed if isinstance(part, str) else part.search(text) for part in parts)
               for parts in self.phrases):
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
        if isinstance(concept, dict) and concept.get("state", "active") != "archived":
            terms += [t for t in concept.get("terms") or () if isinstance(t, str)]
            if isinstance(concept.get("name"), str):
                terms.append(concept["name"])
    return terms

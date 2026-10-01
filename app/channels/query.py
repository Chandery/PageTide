"""Route project keywords to channels by script (ADR 0010).

A Chinese-only index gets only terms that contain Chinese; an English-only API gets no Chinese.
Each channel's actually sent terms are reported, so a user sees why a channel was skipped.
"""
from .text import has_cjk, fold

MAX_TERMS = 3
MAX_TERM_LENGTH = 120


def clean(term):
    return " ".join(fold(str(term or "")).replace(",", " ").replace(":", " ").replace("|", " ").split())[:MAX_TERM_LENGTH]


def terms_for(channel, terms, limit=MAX_TERMS):
    """Terms the channel can use, in the project's order, at most `limit`."""
    scripts = set(channel.scripts)
    picked = []
    for term in terms:
        term = clean(term)
        if not term or term in picked:
            continue
        cjk = has_cjk(term)
        if (cjk and "cjk" in scripts) or (not cjk and "latin" in scripts):
            picked.append(term)
        if len(picked) >= limit:
            break
    return picked

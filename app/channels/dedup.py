"""Cross-channel identity: the same paper found twice must stay one row (ADR 0010).

Order of trust: shared identifiers, then DOI, then (normalized title, year). A title match
needs a year on both sides and a title long enough not to be generic.
"""
import re

from .base import canonical_doi, year_of
from .text import has_cjk, normalize_title

_ARXIV = re.compile(r"(\d{4}\.\d{4,5}|[a-z\-]+(?:\.[a-z]{2})?/\d{7})(?:v\d+)?$", re.I)
MIN_TITLE = 12      # normalized characters
MIN_TITLE_CJK = 6


def arxiv_id(value):
    match = _ARXIV.search(str(value or "").strip())
    return match.group(1).lower() if match else ""


def title_key(title):
    return normalize_title(title)


def title_is_specific(norm):
    return len(norm) >= (MIN_TITLE_CJK if has_cjk(norm) else MIN_TITLE)


def paper_ids(paper):
    """[(scheme, value)] identifying the paper; empty values are skipped."""
    ids = []
    doi = canonical_doi(paper.get("doi"))
    if doi:
        ids.append(("doi", doi))
        match = re.search(r"10\.48550/arxiv\.(.+)$", doi)
        if match and arxiv_id(match.group(1)):
            ids.append(("arxiv", arxiv_id(match.group(1))))
    arxiv = arxiv_id(paper.get("arxiv_id"))
    if arxiv:
        ids.append(("arxiv", arxiv))
    if paper.get("openalex_id"):
        ids.append(("openalex", str(paper["openalex_id"]).rsplit("/", 1)[-1]))
    for scheme, value in (paper.get("ids") or {}).items():
        if value:
            ids.append((str(scheme), str(value)))
    seen, unique = set(), []
    for item in ids:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return unique


def find_existing(conn, paper):
    """Key of the stored paper this one duplicates, or None."""
    if conn.execute("SELECT 1 FROM papers WHERE key=?", (paper["key"],)).fetchone():
        return paper["key"]
    for scheme, value in paper_ids(paper):
        row = conn.execute("SELECT paper_key FROM paper_ids WHERE scheme=? AND value=?", (scheme, value)).fetchone()
        if row:
            return row[0]
    norm, year = title_key(paper.get("title")), year_of(paper.get("published"))
    if title_is_specific(norm) and year:
        row = conn.execute("SELECT key FROM papers WHERE title_norm=? AND year=? ORDER BY created_at LIMIT 1",
                           (norm, year)).fetchone()
        if row:
            return row[0]
    return None

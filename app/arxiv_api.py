"""arXiv's own search API (export.arxiv.org): the arXiv source when OpenAlex has no key, and the fallback when OpenAlex
cannot answer (rate limited, paused or unreachable).

Public metadata only: the search words and a date range go out, nothing else. arXiv asks for no more than one request
every three seconds over a single connection (https://info.arxiv.org/help/api/tou.html); a process-wide lock and clock
keep to it. Results have the shape of sources.slim() and are keyed by the arXiv DOI, the key OpenAlex gives the same
preprint, so a paper found here and later through OpenAlex is one paper.
"""
import datetime
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from .sources import STRICT_MIN_RESULTS, UA, SourceError, clean_query, has_cjk

API = "https://export.arxiv.org/api/query"
GAP_SECONDS = 3.0
TIMEOUT = 20
MAX_BODY = 4 * 1024 * 1024
MAX_WORDS = 8
SOURCE_NAME = "arXiv (Cornell University)"   # the name OpenAlex reports, so both routes label a paper alike
ATOM = "{http://www.w3.org/2005/Atom}"
_LOCK = threading.Lock()
_LAST = [0.0]


def search_query(text, from_date=None, to_date=None, phrase=False):
    """The words as one phrase (phrase=True), or every word anywhere, in the title or the abstract, like OpenAlex's
    title_and_abstract.search; an optional submission-date range. Words are quoted, so nothing in them can change the
    query."""
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9+.-]*", clean_query(text))[:MAX_WORDS]
    if not words:
        return ""
    if phrase:
        joined = " ".join(words)
        query = f'(ti:"{joined}" OR abs:"{joined}")'
    else:
        query = " AND ".join(f'(ti:"{w}" OR abs:"{w}")' for w in words)
    if from_date or to_date:
        start = (from_date or "1991-01-01").replace("-", "")
        end = (to_date or datetime.date.today().isoformat()).replace("-", "")
        query += f" AND submittedDate:[{start}0000 TO {end}2359]"
    return query


def _text(entry, tag):
    node = entry.find(ATOM + tag)
    return re.sub(r"\s+", " ", node.text or "").strip() if node is not None and node.text else ""


def paper_of(entry, group="field"):
    """One Atom entry in upsert_papers shape, or None when it has no arXiv id or title."""
    match = re.search(r"arxiv\.org/abs/(.+?)(?:v\d+)?$", _text(entry, "id"))
    title = _text(entry, "title")
    if not match or not title:
        return None
    arxiv_id = match.group(1).lower()
    doi = f"https://doi.org/10.48550/arxiv.{arxiv_id}"
    authors = [name for name in (_text(a, "name") for a in entry.findall(ATOM + "author")[:6]) if name]
    return {
        "key": doi, "openalex_id": None, "doi": doi, "arxiv_id": arxiv_id, "title": title,
        "abstract": _text(entry, "summary") or None, "published": _text(entry, "published")[:10] or None,
        "work_type": "preprint", "source": SOURCE_NAME, "topic": None, "authors": authors, "group_name": group,
        "oa": {"is_oa": True, "oa_status": "green", "pdf_urls": [f"https://arxiv.org/pdf/{arxiv_id}"],
               "landing_page": f"https://arxiv.org/abs/{arxiv_id}", "license": None, "version": "submittedVersion"},
        # arXiv reports no language; the abstract test in paper_language decides later, as for OpenAlex's arXiv records
        "metadata_language": None, "metadata_language_source": "arXiv",
    }


class ArxivAPI:
    def __init__(self, opener=None, sleep=time.sleep, clock=time.monotonic):
        self._open, self._sleep, self._clock = opener or urllib.request.urlopen, sleep, clock

    def _get(self, url):
        with _LOCK:   # one connection at a time, three seconds apart, across every thread of the app
            wait = _LAST[0] + GAP_SECONDS - self._clock()
            if wait > 0:
                self._sleep(wait)
            try:
                with self._open(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=TIMEOUT) as response:
                    body = response.read(MAX_BODY + 1)
            except urllib.error.HTTPError as exc:
                raise SourceError(f"arXiv HTTP {exc.code}", "unavailable" if exc.code in (429, 503) else "network_error") from None
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                raise SourceError(f"arXiv unreachable: {type(exc).__name__}", "network_error") from None
            finally:
                _LAST[0] = self._clock()
        if len(body) > MAX_BODY:
            raise SourceError("arXiv answer too large", "bad_response")
        if b"<!DOCTYPE" in body or b"<!ENTITY" in body:   # an Atom feed declares neither; refuse entity tricks outright
            raise SourceError("arXiv answer is not a plain Atom feed", "bad_response")
        try:
            return ET.fromstring(body)
        except ET.ParseError:
            raise SourceError("arXiv answer is not XML", "bad_response") from None

    def discover_topic(self, query, per_page=12, from_date=None, to_date=None, order="relevance", page=1, group="field"):
        """Papers whose title or abstract has every word of `query`; newest first for order="recent". Chinese text is
        not searched (arXiv is an English index)."""
        if has_cjk(query):
            return []
        today = datetime.date.today().isoformat()
        to_date = min(str(to_date or today), today)
        if not search_query(query):
            return []
        per_page = max(1, min(int(per_page), 50))
        papers, seen = [], set()

        def ask(search, mode):
            params = {"search_query": search, "start": (max(int(page or 1), 1) - 1) * per_page, "max_results": per_page,
                      "sortBy": "submittedDate" if order == "recent" else "relevance", "sortOrder": "descending"}
            for entry in self._get(f"{API}?{urllib.parse.urlencode(params)}").findall(ATOM + "entry"):
                paper = paper_of(entry, group)
                if not paper or paper["key"] in seen or str(paper["published"] or "") > to_date:
                    continue
                seen.add(paper["key"])
                papers.append({**paper, "match_mode": mode})

        # The words as a phrase first ("world model", not "world" and "model" anywhere); a sparse phrase result is
        # topped up by the every-word search, as OpenAlex's strict search is topped up by its relevance search.
        phrase = search_query(query, from_date, to_date, phrase=True)
        loose = search_query(query, from_date, to_date)
        ask(phrase, "strict")
        if phrase != loose and len(papers) < min(STRICT_MIN_RESULTS, per_page):
            ask(loose, "relevance")
        if order == "recent":
            papers.sort(key=lambda p: str(p.get("published") or ""), reverse=True)
        return papers[:per_page]

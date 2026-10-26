"""OpenAlex metadata adapter: discovery, seed resolution, canonical IDs.

Read-only, public metadata only. No private seed IDs are ever sent to a
recommender service. Responses are cached on disk so a batch can be replayed.
"""
import hashlib
import http.client
import datetime
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://api.openalex.org/works"
ARXIV_SOURCE_ID = "S4306400194"  # OpenAlex source: arXiv (Cornell University)
UA = "PageTide/0.1 (local research; read-only metadata)"
MAILTO = "owner@example.invalid"  # OpenAlex ignores mailto since 2026-02 (API keys replaced the polite pool); kept so cached URLs stay valid
GAP_SECONDS = 2.0
KEYED_GAP_SECONDS = 0.3  # with an API key the allowance is 10x and the limit is 100 requests/second
ALLOWED_DISCOVERY_TYPES = ("article", "preprint", "review", "conference-paper")
STRICT_MIN_RESULTS = 3          # fewer strict matches than this are topped up by a relevance search
MAX_CJK_RELAX = 2       # a Chinese query of several words that finds nothing drops its last word, at most this often
SEARCH_TTL_SECONDS = 24 * 3600  # search results older than this are refetched (the old copy is used if offline)
WORK_TTL_SECONDS = 7 * 24 * 3600  # open-access status changes over time
_CJK = re.compile(r"[\u3400-\u9fff\uf900-\ufaff]")
FIELD_QUERY = "world model"
DISTRACTOR_QUERIES = ["diffusion model", "large language model", "reinforcement learning",
                      "video generation", "image segmentation"]


def abstract_text(inverted):
    if not inverted:
        return ""
    positions = []
    for word, indexes in inverted.items():
        for index in indexes:
            positions.append((index, word))
    positions.sort()
    return " ".join(word for _, word in positions)


SOURCE_PAGE_DOMAINS = {"baidu_scholar": "baidu.com", "baidu_web": "xueshu.baidu.com", "cnki": "kns.cnki.net"}   # a source's own pages: the only hosts its links may point to


def page_url(value, domain, upgrade=False):
    """`value` as an https URL on `domain` (or a subdomain), else None.

    Browsers read some URLs differently from Python's parser (a backslash is a path separator to them, a percent sign or an
    "@" in the host part hides another host), so anything with a backslash, a control character or whitespace is refused and the
    host part must be plain ASCII letters, digits, dots and hyphens with no credentials and no port. The host is returned in
    lower case. `upgrade` turns http into https (a source has been seen to return http links); a link that is already stored is
    only trusted when it is https as it stands."""
    text = value if isinstance(value, str) else ""
    if not text or len(text) > 500 or re.search(r"[\s\\\x00-\x1f\x7f]", text):
        return None
    try:
        parts = urllib.parse.urlsplit(text)
    except ValueError:
        return None
    scheme = "https" if parts.scheme == "http" and upgrade else parts.scheme
    host = parts.netloc.lower()
    if scheme != "https" or not re.fullmatch(r"[a-z0-9.-]+", host):
        return None
    if host != domain and not host.endswith("." + domain):
        return None
    return urllib.parse.urlunsplit((scheme, host, parts.path, parts.query, parts.fragment))


def source_pages(oa):
    """The source pages (for example a Baidu Scholar page) in a paper's open-access facts that are safe to show."""
    pages = []
    for entry in (oa.get("pages") if isinstance(oa, dict) else None) or []:
        domain = SOURCE_PAGE_DOMAINS.get(entry.get("source")) if isinstance(entry, dict) else None
        url = page_url(entry.get("url"), domain) if domain else None
        if url and url not in [p["url"] for p in pages]:
            pages.append({"source": entry["source"], "url": url})
    return pages


def pdf_availability(arxiv_id, oa):
    """Whether a legal PDF is known for a paper: "direct" (arXiv, or an https PDF link OpenAlex reports),
    "page" (only a page: OpenAlex's landing page, or a source page such as Baidu Scholar's, which may need a login)
    or "none". A bare DOI is not a source. `oa` is the dict from slim(), its stored JSON, or None."""
    if isinstance(oa, str):
        try:
            oa = json.loads(oa) if oa.strip() else None
        except ValueError:
            oa = None
    oa = oa if isinstance(oa, dict) else {}
    if arxiv_id or any(isinstance(u, str) and u.startswith("https://") for u in oa.get("pdf_urls") or []):
        return "direct"
    page = oa.get("landing_page")
    if isinstance(page, str) and page.startswith("https://"):
        return "page"
    return "page" if source_pages(oa) else "none"


# File modification times and time.time() come from different clocks on Windows and can differ by a few ms.
CLOCK_SKEW_SECONDS = 2


def window_start(years, today=None):
    """The date `years` years before today as YYYY-MM-DD (29 February becomes 28 February)."""
    today = today or datetime.date.today()
    try:
        return today.replace(year=today.year - years).isoformat()
    except ValueError:
        return today.replace(year=today.year - years, day=28).isoformat()


def _prefer_direct(papers, block=6):
    """Within each block of `block` results keep OpenAlex's relevance order but put papers with a direct
    PDF first. Nothing crosses a block, so a much less relevant paper is never lifted above a relevant one."""
    out = []
    for i in range(0, len(papers), block):
        chunk = papers[i:i + block]
        chunk.sort(key=lambda p: pdf_availability(p.get("arxiv_id"), p.get("oa")) != "direct")  # stable
        out.extend(chunk)
    return out


def has_cjk(text):
    return _CJK.search(str(text or "")) is not None


def clean_query(text, limit=180):
    """Public scientific spelling, bounded and unable to inject OpenAlex filters."""
    from .ranking import scientific_text
    normalized=scientific_text(text).replace("element_", "")
    return re.sub(r"\s+", " ", re.sub(r'[,|:!"\\]', " ", normalized)).strip()[:limit]


def title_key(text):
    """Duplicate key that keeps non-ASCII text (normalize_title would reduce 中文 to nothing)."""
    return re.sub(r"[\W_]+", " ", str(text or "").lower(), flags=re.UNICODE).strip()


def similarity(a, b):
    """Word-set overlap, 0..1: how sure a search hit is the title that was looked for.

    The same measure as creation-pdf.js, so the page and the importer agree on what counts as a match.
    A run of CJK characters is one word, exactly as there."""
    left = set(re.findall(r"[a-z0-9\u4e00-\u9fff]+", str(a or "").lower()))
    right = set(re.findall(r"[a-z0-9\u4e00-\u9fff]+", str(b or "").lower()))
    if not left or not right:
        return 0.0
    shared = len(left & right)
    return shared / (len(left) + len(right) - shared)


def normalize_title(text):
    import re
    text = (text or "").lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def ids_of(work):
    ids = work.get("ids") or {}
    doi = work.get("doi") or ""
    return {
        "openalex_id": work.get("id"),
        "doi": doi,
        "arxiv_id": ids.get("arxiv") or (doi.rsplit("arxiv.", 1)[-1] if "arxiv." in doi else None),
    }


def key_of(work):
    ids = ids_of(work)
    return ids["doi"] or ids["openalex_id"] or normalize_title(work.get("title"))


def oa_of(work):
    """Open-access facts OpenAlex reports for a work, or None when it reports none.

    Only https PDF links are kept; they are candidates, never proof a download is permitted.
    """
    access = work.get("open_access") or {}
    best = work.get("best_oa_location") or {}
    urls = []
    for url in [best.get("pdf_url"), (work.get("primary_location") or {}).get("pdf_url"),
                *(loc.get("pdf_url") for loc in (work.get("locations") or []) if isinstance(loc, dict))]:
        if isinstance(url, str) and url.startswith("https://") and url not in urls:
            urls.append(url)
    if not (access or best or urls):
        return None
    return {"is_oa": bool(access.get("is_oa")), "oa_status": access.get("oa_status"),
            "pdf_urls": urls, "landing_page": best.get("landing_page_url") or access.get("oa_url"),
            "license": best.get("license"), "version": best.get("version")}


def slim(work, group="field"):
    from .paper_language import metadata_code
    ids = ids_of(work)
    abstract = abstract_text(work.get("abstract_inverted_index"))
    topic = ((work.get("primary_topic") or {}).get("display_name")
             or (work.get("primary_topic") or {}).get("field", {}).get("display_name"))
    return {
        "key": key_of(work), "openalex_id": ids["openalex_id"], "doi": ids["doi"],
        "arxiv_id": ids["arxiv_id"], "title": work.get("title"), "abstract": abstract,
        "published": work.get("publication_date"), "work_type": work.get("type"),
        "source": ((work.get("primary_location") or {}).get("source") or {}).get("display_name"),
        "topic": topic,
        "authors": [name for name in ((a.get("author") or {}).get("display_name")
                                      for a in (work.get("authorships") or [])[:6]) if name],
        "group_name": group,
        "oa": oa_of(work),
        "metadata_language": metadata_code(work.get('language')),
        "metadata_language_source": 'OpenAlex',
    }


class SourceError(RuntimeError):
    """A source request failed. kind is one of not_found, network_error, unavailable, invalid_input, bad_response,
    auth_required (the key is missing or refused) or quota_exhausted (the allowance is used up); see source_adapters."""

    def __init__(self, message, kind):
        super().__init__(message)
        self.kind = kind


OA_FIELDS = ("is_oa", "oa_status", "pdf_urls", "landing_page", "license", "version")   # what OpenAlex reports (oa_of)


def _union(old, new, ident):
    out, seen = [], set()
    for item in list(old if isinstance(old, list) else []) + list(new if isinstance(new, list) else []):
        marker = ident(item)
        if marker not in seen:
            seen.add(marker)
            out.append(item)
    return out


def merge_oa(old, new):
    """Open-access facts after a new report. Two sources report them and neither may wipe the other.

    OpenAlex's six fields (OA_FIELDS) are replaced only when the new report carries them (open-access status changes
    over time, so its newest report wins); `pages` (source pages such as a Baidu Scholar page) and `via` (which sources
    reported a page) are combined without duplicates; anything else in the new report is taken as is. A value that is
    not a dict counts as nothing."""
    old = old if isinstance(old, dict) else None
    new = new if isinstance(new, dict) else None
    if new is None:
        return old
    if old is None:
        return dict(new)
    merged = dict(old)
    for key, value in new.items():
        if key == "pages":
            merged[key] = _union(old.get("pages"), value, lambda p: (p.get("source"), p.get("url")) if isinstance(p, dict) else repr(p))
        elif key == "via":
            merged[key] = _union(old.get("via"), value, lambda v: v)
        else:
            merged[key] = value
    return merged


class OpenAlex:
    VERIFY_WORD = "world model"   # fixed public word for the settings page's test button

    def __init__(self, cache_dir, api_key=None):
        self.cache = Path(cache_dir)
        self.cache.mkdir(parents=True, exist_ok=True)
        self.api_key = api_key
        self.rejected_publications = []

    # ---- source adapter interface (app/source_adapters.py); existing callers keep using the methods below
    @property
    def info(self):
        from .source_adapters import OPENALEX_INFO
        return OPENALEX_INFO

    def search(self, query, since=None, page=1, per_page=10):
        """Papers for a query by relevance, in upsert_papers shape (see discover_topic)."""
        return self.discover_topic(query, per_page=per_page, from_date=since, order="relevance", page=max(int(page or 1), 1))

    def verify(self, api_key=None):
        """One fresh request with a fixed public word. The typed key is used instead of the saved one when given.
        Nothing is cached or stored (not even the allowance note)."""
        from .source_adapters import error_for, fetch_json
        key = api_key or self.api_key
        url = f"{API}?{urllib.parse.urlencode({'search': self.VERIFY_WORD, 'per-page': 1})}"
        payload = fetch_json(self._request(url, api_key=key), "OpenAlex", secrets=(key, self.api_key))
        if not isinstance(payload, dict):
            raise error_for("OpenAlex", "bad_response", secrets=(key, self.api_key))
        return {"ok": True}

    def pdf_routes(self, paper):
        from .source_adapters import openalex_routes
        return openalex_routes(paper)

    def _request(self, url, api_key=None):
        """The key goes in a header, only to the OpenAlex API host over https. It is an unredirected
        header, so a redirect cannot carry it elsewhere, and it never appears in a URL, cache key or error."""
        request = urllib.request.Request(url, headers={"User-Agent": UA})
        parts = urllib.parse.urlsplit(url)
        key = api_key or self.api_key
        if key and parts.scheme == "https" and parts.hostname == "api.openalex.org":
            request.add_unredirected_header("Authorization", f"Bearer {key}")
        return request

    def _note_rate_limit(self, headers):
        """Remember OpenAlex's allowance headers; the HTTP server builds a new client per request."""
        try:
            h = {str(k).lower(): v for k, v in headers.items()}
        except (AttributeError, TypeError):
            return
        note = {"observed_at": time.time()}
        for name, key, cast in (("x-ratelimit-limit", "limit", int), ("x-ratelimit-remaining", "remaining", int),
                                ("x-ratelimit-limit-usd", "limit_usd", float), ("x-ratelimit-remaining-usd", "remaining_usd", float),
                                ("x-ratelimit-reset", "reset_seconds", int)):
            try:
                if name in h:
                    note[key] = cast(h[name])
            except (TypeError, ValueError):
                pass  # one unusable header must not discard the others
        if len(note) > 1:
            try:
                (self.cache / "ratelimit.json").write_text(json.dumps(note), encoding="utf-8")
            except OSError:
                pass  # a note about the allowance must never break a lookup

    def rate_limit(self):
        """The allowance seen on the last response ({limit, remaining, ..., observed_at}) or None."""
        try:
            note = json.loads((self.cache / "ratelimit.json").read_text(encoding="utf-8"))
            return note if isinstance(note, dict) and "observed_at" in note else None
        except (OSError, ValueError):
            return None

    def _fetch(self, url, retries=2, ttl=None):
        digest = hashlib.sha256(url.encode()).hexdigest()[:16]
        cached = self.cache / f"{digest}.json"
        stale = None
        if cached.exists():
            try:
                payload = json.loads(cached.read_text(encoding="utf-8"))
                if ttl is None or -CLOCK_SKEW_SECONDS <= time.time() - cached.stat().st_mtime <= ttl:  # a clearly future date (clock moved back) is stale; file times can run a little ahead of time.time() on Windows
                    return payload
                stale = payload  # expired: refetch, but keep it in case OpenAlex cannot be reached
            except ValueError:
                cached.unlink()  # a corrupt cache entry is refetched, not trusted
        last = None
        for attempt in range(retries):
            try:
                with urllib.request.urlopen(self._request(url), timeout=30) as response:
                    body = response.read().decode("utf-8", "replace")
                    self._note_rate_limit(getattr(response, "headers", None) or {})
                try:
                    payload = json.loads(body)
                except ValueError as exc:
                    if stale is not None:
                        return stale  # e.g. a captive-portal page: the expired copy is still the better answer
                    raise SourceError(f"OpenAlex returned a non-JSON body: {url}", "bad_response") from exc
                cached.write_text(body, encoding="utf-8")
                time.sleep(KEYED_GAP_SECONDS if self.api_key else GAP_SECONDS)
                return payload
            except http.client.InvalidURL as exc:
                raise SourceError(f"Invalid OpenAlex identifier: {url}", "invalid_input") from exc
            except urllib.error.HTTPError as exc:
                last = exc
                if exc.code == 404:
                    # A missing identifier will not appear on retry.
                    raise SourceError(f"OpenAlex has no record: {url}", "not_found") from exc
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                try:
                    delay = float(retry_after) if retry_after is not None else GAP_SECONDS * (attempt + 1)
                except (TypeError, ValueError):
                    delay = GAP_SECONDS * (attempt + 1)
                # Bound the wait: a hot shared API must not hang the app.
                time.sleep(min(max(delay, GAP_SECONDS), 10))
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last = exc
                time.sleep(min(GAP_SECONDS * (attempt + 1), 10))
        if stale is not None:
            return stale  # offline or rate limited: an expired answer beats none
        # 429/503 mean OpenAlex is shedding load (e.g. anonymous search paused), not a local network fault.
        busy = isinstance(last, urllib.error.HTTPError) and last.code in (429, 503)
        raise SourceError(f"OpenAlex fetch failed: {url}: {last}", "unavailable" if busy else "network_error")

    def _publication_ok(self, work, to_date=None):
        """Defend even when a cached/upstream answer ignores the date filter; retain raw evidence."""
        published = str(work.get("publication_date") or "")
        cutoff = min(str(to_date or datetime.date.today().isoformat()), datetime.date.today().isoformat())
        try:
            future = datetime.date.fromisoformat(published) > datetime.date.fromisoformat(cutoff)
        except ValueError:
            future = False
        if future:
            self.rejected_publications.append({"key": key_of(work), "published": published,
                                               "reason": "future_publication_date", "source": "OpenAlex"})
            del self.rejected_publications[:-100]
            return False
        return True

    FALLBACK_KINDS = ("unavailable", "network_error", "quota_exhausted")   # OpenAlex could not answer, not "no such paper"
    DOWN_SECONDS = 600   # after an outage the rest of a refresh goes to arXiv at once instead of waiting out OpenAlex again

    @property
    def arxiv(self):
        if getattr(self, "_arxiv", None) is None:
            from .arxiv_api import ArxivAPI
            self._arxiv = ArxivAPI()
        return self._arxiv

    @arxiv.setter
    def arxiv(self, client):
        self._arxiv = client

    def discover_topic(self, query, per_page=12, from_date=None, to_date=None, order="relevance", prefer_pdf=True, page=1,
                       source_arxiv=True, source_openalex=True):
        """Which index answers a topic search. OpenAlex is searched only with a key: without one its allowance is small
        and shared by everyone behind the same address, and anonymous search is sometimes paused. So with no key the arXiv
        switch searches arXiv's own API and journals and conferences are not searched (their row asks for a key). With a
        key, an OpenAlex outage falls back to arXiv's API for the arXiv part."""
        if not source_arxiv and not source_openalex:
            return []
        if self.api_key and time.time() >= getattr(self, "_down_until", 0):
            try:
                return self._openalex_topic(query, per_page, from_date, to_date, order, prefer_pdf, page, source_arxiv, source_openalex)
            except SourceError as exc:
                if not source_arxiv or exc.kind not in self.FALLBACK_KINDS:
                    raise
                self._down_until = time.time() + self.DOWN_SECONDS
        elif not source_arxiv:
            return []
        return self.arxiv.discover_topic(query, per_page=per_page, from_date=from_date, to_date=to_date, order=order, page=page)

    def _openalex_topic(self, query, per_page=12, from_date=None, to_date=None, order="relevance", prefer_pdf=True, page=1,
                        source_arxiv=True, source_openalex=True):
        """Candidate papers for a research topic from OpenAlex, for project creation and per-project refresh.

        English phrases are matched against title AND abstract (every word must appear), in any source
        (journals as well as arXiv). order="relevance" ranks those matches by OpenAlex relevance (project
        creation: the user is choosing); order="recent" sorts them newest first (the daily feed). When fewer
        than STRICT_MIN_RESULTS match, a broader search tops them up, still date-sorted for recent order. A query containing
        Chinese asks for each of its words as an exact phrase and is never topped up (see the note in the code).
        Each paper carries match_mode ("strict" or "relevance"). No date bound unless asked.
        """
        text = clean_query(query)
        if not text:
            return []
        if not source_arxiv and not source_openalex:return []
        to_date = min(str(to_date or datetime.date.today().isoformat()), datetime.date.today().isoformat())
        base = ["type:" + "|".join(ALLOWED_DISCOVERY_TYPES)]
        if not source_openalex:base.append("primary_location.source.id:" + ARXIV_SOURCE_ID)
        elif not source_arxiv:base.append("primary_location.source.id:!" + ARXIV_SOURCE_ID)
        if from_date:
            base.append(f"from_publication_date:{from_date}")
        if to_date:
            base.append(f"to_publication_date:{to_date}")
        papers, seen = [], set()

        def add(works, mode):
            for work in works:
                if not self._publication_ok(work, to_date):continue
                source = ((work.get("primary_location") or {}).get("source") or {}).get("id", "")
                is_arxiv = str(source).endswith(ARXIV_SOURCE_ID) or bool(ids_of(work)["arxiv_id"])
                if (is_arxiv and not source_arxiv) or (not is_arxiv and not source_openalex):continue
                if work.get("type") and work["type"] not in ALLOWED_DISCOVERY_TYPES:continue
                paper = slim(work, group="field")
                title = title_key(work.get("title")) or paper["key"]
                if not work.get("title") or paper["key"] in seen or title in seen:
                    continue
                seen.update({paper["key"], title})
                papers.append({**paper, "match_mode": mode})

        if has_cjk(text):
            # OpenAlex's relevance search splits Chinese into single characters: of the newest 25 results for 语法教学,
            # 二语习得 or 汉语语法, none mentioned the term; asked for the exact phrase, 21-25 of 25 did (measured with the
            # owner's key, 2026-10-26). So each word of a Chinese query is an exact phrase, all required (a repeated filter is
            # an AND); when that finds nothing, the last word is dropped, at most MAX_CJK_RELAX times. No fuzzy fallback.
            phrases = [w.replace('"', "") for w in text.split() if w.replace('"', "")]
            for _ in range(MAX_CJK_RELAX + 1):
                params = {"filter": ",".join([*(f'title_and_abstract.search:"{w}"' for w in phrases), *base]),
                          "per-page": per_page, "mailto": MAILTO}
                if page > 1:
                    params["page"] = int(page)
                if order == "recent":
                    params["sort"] = "publication_date:desc"
                add(self._fetch(f"{API}?{urllib.parse.urlencode(params)}", ttl=SEARCH_TTL_SECONDS).get("results", []), "strict")
                if papers or len(phrases) == 1 or page > 1:
                    break
                phrases = phrases[:-1]
        else:
            params = {"filter": ",".join([f"title_and_abstract.search:{text}", *base]), "per-page": per_page, "mailto": MAILTO}
            if page > 1:
                params["page"] = int(page)
            if order == "recent":
                params["sort"] = "publication_date:desc"
            else:
                params["search"] = text
            add(self._fetch(f"{API}?{urllib.parse.urlencode(params)}", ttl=SEARCH_TTL_SECONDS).get("results", []), "strict")
        if len(papers) < min(STRICT_MIN_RESULTS, per_page) and not has_cjk(text):
            params = {"search": text, "filter": ",".join(base), "per-page": per_page, "mailto": MAILTO}
            if page > 1:
                params["page"] = int(page)
            if order == "recent":
                params["sort"] = "publication_date:desc"
            add(self._fetch(f"{API}?{urllib.parse.urlencode(params)}", ttl=SEARCH_TTL_SECONDS).get("results", []), "relevance")
        if order == "recent":
            papers.sort(key=lambda p: str(p.get('published') or ''), reverse=True)
        if prefer_pdf and order == "relevance":
            papers = _prefer_direct(papers)
        return papers[:per_page]

    def discover(self, search=FIELD_QUERY, from_date="2024-01-01", to_date=None, pages=1, per_page=100,
                 source_id=ARXIV_SOURCE_ID):
        """Discovery recipe validated in DATA-01: arXiv source + title.search + date bounds.

        Stops early on the first persistent failure so a hot shared API cannot hang the app. Without an OpenAlex key
        (see discover_topic) arXiv's own API answers instead, newest first.
        """
        import datetime
        to_date = min(str(to_date or datetime.date.today().isoformat()), datetime.date.today().isoformat())
        if not self.api_key and source_id == ARXIV_SOURCE_ID:
            return self.arxiv.discover_topic(search, per_page=min(int(per_page), 50), from_date=from_date, to_date=to_date, order="recent")
        works, seen = [], set()
        for page in range(1, pages + 1):
            params = {
                "filter": (f"primary_location.source.id:{source_id},title.search:{search}," +
                           (f"from_publication_date:{from_date}," if from_date else "") + f"to_publication_date:{to_date}"),
                "sort": "publication_date:desc", "per-page": per_page, "page": page, "mailto": MAILTO,
            }
            payload = self._fetch(f"{API}?{urllib.parse.urlencode(params)}", ttl=SEARCH_TTL_SECONDS)
            for work in payload.get("results", []):
                title = normalize_title(work.get("title"))
                if title in seen:
                    continue
                seen.add(title)
                if self._publication_ok(work, to_date):works.append(slim(work, group="field"))
        return works

    def distractors(self, from_date="2024-01-01", to_date=None, per_query=40, source_id=ARXIV_SOURCE_ID):
        import datetime
        to_date = min(str(to_date or datetime.date.today().isoformat()), datetime.date.today().isoformat())
        works, errors = [], []
        for query in DISTRACTOR_QUERIES:
            params = {
                "filter": (f"primary_location.source.id:{source_id},title.search:{query}," +
                           (f"from_publication_date:{from_date}," if from_date else "") + f"to_publication_date:{to_date}"),
                "sort": "publication_date:desc", "per-page": per_query, "page": 1, "mailto": MAILTO,
            }
            try:
                payload = self._fetch(f"{API}?{urllib.parse.urlencode(params)}", ttl=SEARCH_TTL_SECONDS)
            except RuntimeError as exc:
                errors.append({"query": query, "error": str(exc)[-120:]})
                break  # hot API: stop instead of stacking retries
            for work in payload.get("results", []):
                if self._publication_ok(work, to_date):works.append(slim(work, group="distractor"))
        return works, errors

    def work(self, identifier):
        """Fetch one work by DOI URL, OpenAlex ID or W-id. Used for seed resolution."""
        # Quote so a stray "?", "#" or space cannot change which request is made.
        return self._fetch(f"{API}/{urllib.parse.quote(identifier, safe=':/')}?mailto={urllib.parse.quote(MAILTO)}",
                           ttl=WORK_TTL_SECONDS)

    def search_works(self, query, per_page=8):
        """Papers by name for the manual seed picker (an explicit user query).

        Two requests: a title match (fetched wider than shown, because the real paper may not be first) and
        OpenAlex's relevance search. The union is ranked by how well each title matches what was typed, so the
        paper itself comes before "Fast ..." variants (a bare relevance search ranked "Fast LeWorldModel" above
        LeWorldModel). No source or date restriction: a seed may be older or outside arXiv. Only the typed
        text is sent, as a public metadata query.
        """
        text = clean_query(query)
        if not text:
            return []
        found, seen = [], set()

        def add(works):
            for work in works:
                paper = slim(work, group="seed")
                title = title_key(work.get("title"))
                if work.get("title") and paper["key"] not in seen and title not in seen:  # one line per distinct title
                    seen.update({paper["key"], title})
                    found.append(paper)

        try:
            exact = {"filter": f"title.search:{text}", "per-page": max(int(per_page), 25), "mailto": MAILTO}
            add(self._fetch(f"{API}?{urllib.parse.urlencode(exact)}", ttl=SEARCH_TTL_SECONDS).get("results", []))
        except SourceError:
            pass  # the relevance search below still answers (and reports a real outage)
        relevance = {"search": text, "per-page": per_page, "mailto": MAILTO}
        add(self._fetch(f"{API}?{urllib.parse.urlencode(relevance)}", ttl=SEARCH_TTL_SECONDS).get("results", []))
        wanted = normalize_title(text)

        def rank(paper):
            title = normalize_title(paper["title"])
            if title == wanted:
                return 3
            if wanted and title.startswith(wanted):
                return 2
            return 1 if wanted and wanted in title else 0
        found.sort(key=rank, reverse=True)  # stable: equal ranks keep OpenAlex's order
        return found[:per_page]

    def find_arxiv(self, arxiv_id):
        """Find an arXiv paper by its landing page when OpenAlex lacks the arXiv DOI (common before 2022).

        Only the http:// form is indexed; the https:// form times out on OpenAlex.
        """
        params = {"filter": f"locations.landing_page_url:http://arxiv.org/abs/{arxiv_id}",
                  "per-page": 1, "mailto": MAILTO}
        results = self._fetch(f"{API}?{urllib.parse.urlencode(params)}").get("results") or []
        if not results:
            raise SourceError(f"OpenAlex has no arXiv record: {arxiv_id}", "not_found")
        return results[0]

    @staticmethod
    def _wrong_request(exc):
        """An HTTP 4xx answer (other than being rate limited) says the request itself was wrong, not that the network is
        down: pausing and retrying the same request would stall an import for ever on one odd identifier."""
        text = str(exc)
        if exc.kind == "network_error" and re.search(r"HTTP Error 4\d\d\b", text) and "HTTP Error 429" not in text:
            return SourceError(text, "invalid_input")
        return exc

    def works_by_dois(self, dois):
        """Works for a list of DOI URLs in one request (OR filter). Callers pass at most 50 DOIs, none of which
        contains ',' or '|' (those would change the filter); a DOI OpenAlex does not know is simply absent."""
        dois = [d for d in dict.fromkeys(dois) if d and "," not in d and "|" not in d]
        if not dois:
            return []
        params = {"filter": "doi:" + "|".join(dois), "per-page": min(max(len(dois), 1), 200), "mailto": MAILTO}
        try:
            return self._fetch(f"{API}?{urllib.parse.urlencode(params)}", ttl=WORK_TTL_SECONDS).get("results") or []
        except SourceError as exc:
            raise self._wrong_request(exc) from None

    def title_lookup(self, title, per_page=5):
        """Works whose title matches a title read from a PDF: one title filter request, and a relevance search
        only when the filter finds nothing (a noisy extracted title rarely contains every word of the real one).
        Only the title text leaves the machine, as a public metadata query."""
        text = clean_query(title)
        if not text:
            return []
        exact = {"filter": f"title.search:{text}", "per-page": per_page, "mailto": MAILTO}
        relevance = {"search": text, "per-page": per_page, "mailto": MAILTO}
        try:
            found = self._fetch(f"{API}?{urllib.parse.urlencode(exact)}", ttl=SEARCH_TTL_SECONDS).get("results") or []
            if found:
                return found
            return self._fetch(f"{API}?{urllib.parse.urlencode(relevance)}", ttl=SEARCH_TTL_SECONDS).get("results") or []
        except SourceError as exc:
            raise self._wrong_request(exc) from None


def fetch_seed_work(client, identifier, arxiv_id=None):
    """Fetch one seed work; an arXiv DOI missing from OpenAlex falls back to the landing page."""
    try:
        return client.work(identifier)
    except SourceError as exc:
        if exc.kind != "not_found" or not arxiv_id:
            raise
    return client.find_arxiv(arxiv_id)


def resolve_seed(client, seed):
    """Resolve a seed dict {title, ids:{...}} to a slim paper, or None."""
    ids = seed.get("ids") or {}
    identifier = None
    if ids.get("arxiv_id"):
        identifier = f"https://doi.org/10.48550/arxiv.{ids['arxiv_id']}"
    elif ids.get("openalex_id"):
        identifier = ids["openalex_id"]
    elif ids.get("doi"):
        identifier = f"https://doi.org/{ids['doi']}"
    if identifier:
        work = fetch_seed_work(client, identifier, ids.get("arxiv_id"))
        paper = slim(work, group="seed")
        paper["arxiv_id"] = paper["arxiv_id"] or ids.get("arxiv_id")
        paper["seed_title"] = seed["title"]
        paper["title_matches"] = normalize_title(work.get("title")) == normalize_title(seed["title"])
        return paper
    return None

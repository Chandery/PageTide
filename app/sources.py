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
UA = "PaperDigHelper/0.1 (local research; read-only metadata)"
MAILTO = "owner@example.invalid"  # OpenAlex ignores mailto since 2026-02 (API keys replaced the polite pool); kept so cached URLs stay valid
GAP_SECONDS = 2.0
KEYED_GAP_SECONDS = 0.3  # with an API key the allowance is 10x and the limit is 100 requests/second
STRICT_MIN_RESULTS = 3          # fewer strict matches than this are topped up by a relevance search
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


def pdf_availability(arxiv_id, oa):
    """Whether a legal PDF is known for a paper: "direct" (arXiv, or an https PDF link OpenAlex reports),
    "page" (open access but only a landing page) or "none". `oa` is the dict from slim(), its stored JSON, or None."""
    if isinstance(oa, str):
        try:
            oa = json.loads(oa) if oa.strip() else None
        except ValueError:
            oa = None
    oa = oa if isinstance(oa, dict) else {}
    if arxiv_id or any(isinstance(u, str) and u.startswith("https://") for u in oa.get("pdf_urls") or []):
        return "direct"
    page = oa.get("landing_page")
    return "page" if isinstance(page, str) and page.startswith("https://") else "none"


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
    """A search phrase that cannot change the structure of an OpenAlex filter (',' '|' ':' and quotes)."""
    return re.sub(r"\s+", " ", re.sub(r"[,|:!\"\\]", " ", str(text or ""))).strip()[:limit]


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
        "published": work.get("publication_date"),
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
    """A public-metadata fetch failed; kind is not_found, network_error, unavailable, invalid_input or bad_response."""

    def __init__(self, message, kind):
        super().__init__(message)
        self.kind = kind


class OpenAlex:
    def __init__(self, cache_dir, api_key=None):
        self.cache = Path(cache_dir)
        self.cache.mkdir(parents=True, exist_ok=True)
        self.api_key = api_key

    def _request(self, url):
        """The key goes in a header, only to the OpenAlex API host over https. It is an unredirected
        header, so a redirect cannot carry it elsewhere, and it never appears in a URL, cache key or error."""
        request = urllib.request.Request(url, headers={"User-Agent": UA})
        parts = urllib.parse.urlsplit(url)
        if self.api_key and parts.scheme == "https" and parts.hostname == "api.openalex.org":
            request.add_unredirected_header("Authorization", f"Bearer {self.api_key}")
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
                (self.cache / "ratelimit.json").write_text(json.dumps(note))
            except OSError:
                pass  # a note about the allowance must never break a lookup

    def rate_limit(self):
        """The allowance seen on the last response ({limit, remaining, ..., observed_at}) or None."""
        try:
            note = json.loads((self.cache / "ratelimit.json").read_text())
            return note if isinstance(note, dict) and "observed_at" in note else None
        except (OSError, ValueError):
            return None

    def _fetch(self, url, retries=2, ttl=None):
        digest = hashlib.sha256(url.encode()).hexdigest()[:16]
        cached = self.cache / f"{digest}.json"
        stale = None
        if cached.exists():
            try:
                payload = json.loads(cached.read_text())
                if ttl is None or 0 <= time.time() - cached.stat().st_mtime <= ttl:  # a future date (clock moved back) is stale
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
                cached.write_text(body)
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

    def discover_topic(self, query, per_page=12, from_date=None, to_date=None, order="relevance", prefer_pdf=True, page=1):
        """Candidate papers for a research topic, for project creation and per-project refresh.

        English phrases are matched against title AND abstract (every word must appear), in any source
        (journals as well as arXiv). order="relevance" ranks those matches by OpenAlex relevance (project
        creation: the user is choosing); order="recent" sorts them newest first (the daily feed). When fewer
        than STRICT_MIN_RESULTS match, a broader search tops them up, still date-sorted for recent order. A phrase containing Chinese
        goes straight to relevance search, since title matching on an English-titled index finds nothing.
        Each paper carries match_mode ("strict" or "relevance"). No date bound unless asked.
        """
        text = clean_query(query)
        if not text:
            return []
        base = ["type:article|preprint"]
        if from_date:
            base.append(f"from_publication_date:{from_date}")
        if to_date:
            base.append(f"to_publication_date:{to_date}")
        papers, seen = [], set()

        def add(works, mode):
            for work in works:
                paper = slim(work, group="field")
                title = title_key(work.get("title")) or paper["key"]
                if not work.get("title") or paper["key"] in seen or title in seen:
                    continue
                seen.update({paper["key"], title})
                papers.append({**paper, "match_mode": mode})

        if not has_cjk(text):
            params = {"filter": ",".join([f"title_and_abstract.search:{text}", *base]), "per-page": per_page, "mailto": MAILTO}
            if page > 1:
                params["page"] = int(page)
            if order == "recent":
                params["sort"] = "publication_date:desc"
            else:
                params["search"] = text
            add(self._fetch(f"{API}?{urllib.parse.urlencode(params)}", ttl=SEARCH_TTL_SECONDS).get("results", []), "strict")
        if len(papers) < min(STRICT_MIN_RESULTS, per_page):
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

        Stops early on the first persistent failure so a hot shared API cannot hang the app.
        """
        import datetime
        to_date = to_date or datetime.date.today().isoformat()
        works, seen = [], set()
        for page in range(1, pages + 1):
            params = {
                "filter": (f"primary_location.source.id:{source_id},title.search:{search},"
                           f"from_publication_date:{from_date},to_publication_date:{to_date}"),
                "sort": "publication_date:desc", "per-page": per_page, "page": page, "mailto": MAILTO,
            }
            payload = self._fetch(f"{API}?{urllib.parse.urlencode(params)}", ttl=SEARCH_TTL_SECONDS)
            for work in payload.get("results", []):
                title = normalize_title(work.get("title"))
                if title in seen:
                    continue
                seen.add(title)
                works.append(slim(work, group="field"))
        return works

    def distractors(self, from_date="2024-01-01", to_date=None, per_query=40, source_id=ARXIV_SOURCE_ID):
        import datetime
        to_date = to_date or datetime.date.today().isoformat()
        works, errors = [], []
        for query in DISTRACTOR_QUERIES:
            params = {
                "filter": (f"primary_location.source.id:{source_id},title.search:{query},"
                           f"from_publication_date:{from_date},to_publication_date:{to_date}"),
                "sort": "publication_date:desc", "per-page": per_query, "page": 1, "mailto": MAILTO,
            }
            try:
                payload = self._fetch(f"{API}?{urllib.parse.urlencode(params)}", ttl=SEARCH_TTL_SECONDS)
            except RuntimeError as exc:
                errors.append({"query": query, "error": str(exc)[-120:]})
                break  # hot API: stop instead of stacking retries
            for work in payload.get("results", []):
                works.append(slim(work, group="distractor"))
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

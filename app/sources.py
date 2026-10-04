"""OpenAlex metadata adapter: discovery, seed resolution, canonical IDs.

Read-only, public metadata only. No private seed IDs are ever sent to a
recommender service. Responses are cached on disk so a batch can be replayed.
"""
import hashlib
import http.client
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

    def _fetch(self, url, retries=2):
        digest = hashlib.sha256(url.encode()).hexdigest()[:16]
        cached = self.cache / f"{digest}.json"
        if cached.exists():
            try:
                return json.loads(cached.read_text())
            except ValueError:
                cached.unlink()  # a corrupt cache entry is refetched, not trusted
        last = None
        for attempt in range(retries):
            try:
                with urllib.request.urlopen(self._request(url), timeout=30) as response:
                    body = response.read().decode("utf-8", "replace")
                try:
                    payload = json.loads(body)
                except ValueError as exc:
                    raise SourceError(f"OpenAlex returned a non-JSON body: {url}", "bad_response") from exc
                cached.write_text(body)
                time.sleep(GAP_SECONDS)
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
        # 429/503 mean OpenAlex is shedding load (e.g. anonymous search paused), not a local network fault.
        busy = isinstance(last, urllib.error.HTTPError) and last.code in (429, 503)
        raise SourceError(f"OpenAlex fetch failed: {url}: {last}", "unavailable" if busy else "network_error")

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
            payload = self._fetch(f"{API}?{urllib.parse.urlencode(params)}")
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
                payload = self._fetch(f"{API}?{urllib.parse.urlencode(params)}")
            except RuntimeError as exc:
                errors.append({"query": query, "error": str(exc)[-120:]})
                break  # hot API: stop instead of stacking retries
            for work in payload.get("results", []):
                works.append(slim(work, group="distractor"))
        return works, errors

    def work(self, identifier):
        """Fetch one work by DOI URL, OpenAlex ID or W-id. Used for seed resolution."""
        # Quote so a stray "?", "#" or space cannot change which request is made.
        return self._fetch(f"{API}/{urllib.parse.quote(identifier, safe=':/')}?mailto={urllib.parse.quote(MAILTO)}")

    def search_works(self, query, per_page=8):
        """Relevance search by paper name for the manual seed picker (an explicit user query).

        No source or date restriction: a seed may be older or outside arXiv. Only the typed
        text is sent, as a public metadata query.
        """
        params = {"search": query, "per-page": per_page, "mailto": MAILTO}
        payload = self._fetch(f"{API}?{urllib.parse.urlencode(params)}")
        return [slim(work, group="seed") for work in payload.get("results", []) if work.get("title")]

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

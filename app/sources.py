"""OpenAlex metadata adapter: discovery, seed resolution, canonical IDs.

Read-only, public metadata only. No private seed IDs are ever sent to a
recommender service. Responses are cached on disk so a batch can be replayed.
"""
import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://api.openalex.org/works"
ARXIV_SOURCE_ID = "S4306400194"  # OpenAlex source: arXiv (Cornell University)
UA = "PaperDigHelper/0.1 (local research; read-only metadata)"
MAILTO = "owner@example.invalid"  # replace with the owner's contact for heavier use
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
        "group_name": group,
    }


class OpenAlex:
    def __init__(self, cache_dir):
        self.cache = Path(cache_dir)
        self.cache.mkdir(parents=True, exist_ok=True)

    def _fetch(self, url, retries=2):
        digest = hashlib.sha256(url.encode()).hexdigest()[:16]
        cached = self.cache / f"{digest}.json"
        if cached.exists():
            return json.loads(cached.read_text())
        last = None
        for attempt in range(retries):
            try:
                request = urllib.request.Request(url, headers={"User-Agent": UA})
                with urllib.request.urlopen(request, timeout=30) as response:
                    body = response.read().decode("utf-8", "replace")
                cached.write_text(body)
                time.sleep(GAP_SECONDS)
                return json.loads(body)
            except urllib.error.HTTPError as exc:
                last = exc
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
        raise RuntimeError(f"OpenAlex fetch failed: {url}: {last}")

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
        return self._fetch(f"{API}/{identifier}?mailto={urllib.parse.quote(MAILTO)}")


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
        work = client.work(identifier)
        paper = slim(work, group="seed")
        paper["seed_title"] = seed["title"]
        paper["title_matches"] = normalize_title(work.get("title")) == normalize_title(seed["title"])
        return paper
    return None

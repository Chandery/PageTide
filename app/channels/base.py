"""Channel contract (ADR 0010): one class per paper source, parsing kept in pure functions.

A channel turns one search term into paper dicts of the shape the database stores:
key, title, abstract, published, doi, arxiv_id, openalex_id, source, topic, group_name
plus language, url, pdf_url, channel, authors. Parsing lives in module-level
`parse_*` functions so fixtures can test it without a network.
"""
import re
from dataclasses import dataclass, field
from pathlib import Path

from .http import Client, SourceError  # noqa: F401  (SourceError re-exported for channel modules)
from .text import detect_language, normalize_title

DOI_PREFIX = "https://doi.org/"
_DOI = re.compile(r"10\.\d{4,9}/\S+", re.I)


def canonical_doi(value):
    """'https://doi.org/10.1/ABC' for any DOI spelling, or '' when there is none."""
    match = _DOI.search(str(value or ""))
    if not match:
        return ""
    return DOI_PREFIX + match.group().rstrip(".,;)").lower()


def collapse(text):
    return re.sub(r"\s+", " ", str(text or "")).strip()


def year_of(published):
    match = re.match(r"(\d{4})", str(published or ""))
    return int(match.group(1)) if match else None


def make_paper(channel, title, *, doi="", abstract="", published=None, authors=None, source=None,
               topic=None, url=None, pdf_url=None, arxiv_id=None, openalex_id=None,
               native_id=None, language=None):
    """Paper dict for upsert_papers. The key is the DOI when there is one, so a paper found through
    two channels lands on one row; otherwise '<channel>:<native id>', otherwise the title key."""
    title = collapse(title)
    doi = canonical_doi(doi)
    abstract = collapse(abstract)
    if doi:
        key = doi
    elif openalex_id:
        key = openalex_id
    elif native_id:
        key = f"{channel}:{native_id}"
    else:
        key = normalize_title(title)
    return {
        "key": key, "openalex_id": openalex_id, "doi": doi or None, "arxiv_id": arxiv_id,
        "title": title, "abstract": abstract, "published": published, "source": source,
        "topic": topic, "group_name": "field", "channel": channel,
        "authors": [collapse(a) for a in (authors or []) if collapse(a)],
        "url": url, "pdf_url": pdf_url,
        "language": language or detect_language(f"{title} {abstract}"),
    }


@dataclass
class Context:
    """What a channel may use: a cache directory, credentials by (channel, field) and a contact address."""
    cache_dir: Path
    credentials: object = None  # callable(channel_id, field) -> str | None
    contact: str = "owner@example.invalid"
    clients: dict = field(default_factory=dict)

    def credential(self, channel_id, name):
        return self.credentials(channel_id, name) if self.credentials else None

    def client(self, channel_id, gap):
        if channel_id not in self.clients:
            self.clients[channel_id] = Client(Path(self.cache_dir) / channel_id, label=channel_id, gap=gap)
        return self.clients[channel_id]


class Channel:
    id = ""
    name = ""
    tier = "A"                   # A public API, B own API key, C login session, D link-out
    auth = "none"                # none | api_key | session
    disciplines = ()
    languages = ("en",)
    scripts = ("latin",)         # which kinds of search terms the channel can use: latin, cjk
    gap = 2.0                    # seconds between requests to the channel's host
    daily_cap = 60               # provisional per-day request ceiling (not owner-approved)
    terms_url = ""
    site_url = ""
    capabilities = ("search",)

    def search(self, ctx, term, since, limit):
        """Return paper dicts for one search term; raise SourceError on failure."""
        raise NotImplementedError

    def landing_url(self, paper):
        return paper.get("url")

"""OpenAlex channel. Since 2026-02-13 OpenAlex expects a per-user API key (source: OPENALEX)."""
import urllib.parse

from .base import Channel, SourceError, canonical_doi, collapse, make_paper
from .http import SEARCH_TTL
from .dedup import arxiv_id
from ..sources import abstract_text

API = "https://api.openalex.org/works"


def parse_works(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise SourceError("OpenAlex returned JSON without a results list", "bad_response")
    papers = []
    for work in payload["results"]:
        title = collapse(work.get("title") or work.get("display_name"))
        if not title:
            continue
        ids = work.get("ids") or {}
        location = work.get("primary_location") or {}
        topic = work.get("primary_topic") or {}
        best = work.get("best_oa_location") or {}
        arxiv = arxiv_id(ids.get("arxiv")) or arxiv_id(work.get("doi"))
        papers.append(make_paper(
            "openalex", title, doi=work.get("doi") or "",
            abstract=abstract_text(work.get("abstract_inverted_index")),
            published=work.get("publication_date"),
            authors=[(a.get("author") or {}).get("display_name") for a in work.get("authorships") or []],
            source=(location.get("source") or {}).get("display_name"),
            topic=topic.get("display_name") or (topic.get("field") or {}).get("display_name"),
            url=location.get("landing_page_url") or canonical_doi(work.get("doi")) or work.get("id"),
            pdf_url=best.get("pdf_url") or location.get("pdf_url"),
            arxiv_id=arxiv or None, openalex_id=work.get("id"),
            language=work.get("language")))
    return papers


class OpenAlexChannel(Channel):
    id = "openalex"
    name = "OpenAlex"
    disciplines = ("cs_ai", "biomed", "physics_chem", "econ_mgmt", "humanities_social_cn", "education")
    languages = ("en", "zh", "other")
    scripts = ("latin", "cjk")
    gap = 2.0
    daily_cap = 60  # a search costs ~10 of the 1000 daily credits observed on 2026-09-11
    terms_url = "https://developers.openalex.org/"
    site_url = "https://openalex.org"

    def search(self, ctx, term, since, limit):
        params = {"filter": f"title_and_abstract.search:{term},from_publication_date:{since}",
                  "sort": "publication_date:desc", "per-page": min(int(limit), 100),
                  "mailto": ctx.contact}
        key = ctx.credential(self.id, "api_key")
        if key:
            params["api_key"] = key
        payload = ctx.client(self.id, self.gap).get(f"{API}?{urllib.parse.urlencode(params)}", ttl=SEARCH_TTL)
        return parse_works(payload)

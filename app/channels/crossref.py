"""Crossref REST channel (public; the polite pool is reached by sending a contact address)."""
import re
import urllib.parse

from .base import Channel, SourceError, collapse, make_paper
from .http import SEARCH_TTL

API = "https://api.crossref.org/works"
_TAGS = re.compile(r"<[^>]+>")


def _date(item):
    for field in ("published", "published-print", "published-online", "issued"):
        parts = ((item.get(field) or {}).get("date-parts") or [[None]])[0]
        if parts and parts[0]:
            return "-".join(f"{int(p):02d}" if i else str(int(p)) for i, p in enumerate(parts[:3]))
    return None


def _full_date(value):
    """'2024' or '2024-05' -> an ISO date the rest of the app sorts correctly."""
    if not value:
        return None
    parts = value.split("-")
    return "-".join([parts[0], parts[1] if len(parts) > 1 else "01", parts[2] if len(parts) > 2 else "01"])


def parse_works(payload):
    message = payload.get("message") if isinstance(payload, dict) else None
    items = message.get("items") if isinstance(message, dict) else None
    if not isinstance(items, list):
        raise SourceError("Crossref returned JSON without message.items", "bad_response")
    papers = []
    for item in items:
        title = collapse(" ".join(item.get("title") or []))
        if not title or not item.get("DOI"):
            continue
        authors = [collapse(f"{a.get('given', '')} {a.get('family', '')}") or a.get("name", "")
                   for a in item.get("author") or []]
        pdf = next((l.get("URL") for l in item.get("link") or []
                    if l.get("content-type") == "application/pdf"), None)
        papers.append(make_paper(
            "crossref", title, doi=item["DOI"],
            abstract=_TAGS.sub(" ", item.get("abstract") or ""),
            published=_full_date(_date(item)), authors=authors,
            source=collapse(" ".join(item.get("container-title") or [])) or None,
            topic=(item.get("subject") or [None])[0], url=item.get("URL"), pdf_url=pdf,
            language=item.get("language")))
    return papers


class Crossref(Channel):
    id = "crossref"
    name = "Crossref"
    disciplines = ("cs_ai", "biomed", "physics_chem", "econ_mgmt", "humanities_social_cn", "education")
    languages = ("en", "zh", "other")
    scripts = ("latin", "cjk")
    gap = 1.0
    daily_cap = 120
    terms_url = "https://www.crossref.org/documentation/retrieve-metadata/rest-api/"
    site_url = "https://www.crossref.org"

    def search(self, ctx, term, since, limit):
        params = {"query.bibliographic": term, "filter": f"from-pub-date:{since}",
                  "rows": min(int(limit), 100), "mailto": ctx.contact,
                  "select": "DOI,title,abstract,author,issued,published,container-title,URL,subject,language,link"}
        payload = ctx.client(self.id, self.gap).get(f"{API}?{urllib.parse.urlencode(params)}", ttl=SEARCH_TTL)
        return parse_works(payload)

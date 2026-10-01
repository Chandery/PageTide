"""arXiv Atom API channel (public, no key). Source: CH-ARXIV-API."""
import urllib.parse
import xml.etree.ElementTree as ET

from .base import Channel, SourceError, collapse, make_paper
from .dedup import arxiv_id
from .http import SEARCH_TTL

API = "https://export.arxiv.org/api/query"
NS = {"a": "http://www.w3.org/2005/Atom", "x": "http://arxiv.org/schemas/atom"}


def parse_feed(body):
    """Paper dicts from an Atom feed. Entities and DTDs are refused: the feed is untrusted input."""
    head = body[:2048].lower()
    if "<!doctype" in head or "<!entity" in body.lower():
        raise SourceError("arXiv returned a feed with a DTD; refused", "bad_response")
    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        raise SourceError("arXiv returned a body that is not an Atom feed", "bad_response") from exc
    if not root.tag.endswith("feed"):
        raise SourceError("arXiv returned a body that is not an Atom feed", "bad_response")
    papers = []
    for entry in root.findall("a:entry", NS):
        link = collapse(entry.findtext("a:id", "", NS))
        ident = arxiv_id(link)
        title = collapse(entry.findtext("a:title", "", NS))
        if not ident or not title or title.lower() == "error":
            continue  # arXiv reports a bad query as a feed with one entry titled "Error"
        pdf = next((l.get("href") for l in entry.findall("a:link", NS) if l.get("title") == "pdf"), None)
        category = entry.find("x:primary_category", NS)
        papers.append(make_paper(
            "arxiv", title,
            doi=collapse(entry.findtext("x:doi", "", NS)) or f"10.48550/arxiv.{ident}",
            abstract=entry.findtext("a:summary", "", NS),
            published=collapse(entry.findtext("a:published", "", NS))[:10] or None,
            authors=[a.findtext("a:name", "", NS) for a in entry.findall("a:author", NS)],
            source="arXiv", topic=category.get("term") if category is not None else None,
            url=f"https://arxiv.org/abs/{ident}", pdf_url=(pdf or f"https://arxiv.org/pdf/{ident}").replace("http://", "https://"),
            arxiv_id=ident, native_id=ident, language="en"))
    return papers


class ArXiv(Channel):
    id = "arxiv"
    name = "arXiv"
    disciplines = ("cs_ai", "physics_chem")
    scripts = ("latin",)
    gap = 3.0  # arXiv legacy terms: one request per three seconds, single connection
    daily_cap = 100
    terms_url = "https://info.arxiv.org/help/api/tou.html"
    site_url = "https://arxiv.org"

    def search(self, ctx, term, since, limit):
        params = {"search_query": f'all:"{term.replace(chr(34), " ")}"', "sortBy": "submittedDate", "sortOrder": "descending",
                  "max_results": min(int(limit), 100)}
        body = ctx.client(self.id, self.gap).get(f"{API}?{urllib.parse.urlencode(params)}",
                                                   ttl=SEARCH_TTL, parse="text")
        papers = parse_feed(body)
        return [p for p in papers if not since or (p["published"] or "9999") >= since]

"""Source adapter interface: what every paper source says about itself and how new code talks to it.

A source is a place papers come from (arXiv and journals through OpenAlex, Baidu Scholar, Baidu AI Search on xueshu.baidu.com). `SourceInfo` constants are
the single truth about a source: whether it needs a key, where the key comes from, what it gives, what is sent to the
provider and what the daily allowance is. docs/SOURCES.md is written from them and a unit test fails when the two
disagree. Existing callers keep talking to `App.source` (the OpenAlex client); only new code uses the registry
`App.adapters`.

Adapter protocol (duck typed; `BaiduScholar`, `BaiduWeb` and `sources.OpenAlex` follow it):
    info                                   the SourceInfo
    search(query, since=None, page=1, per_page=10) -> list of dicts in the shape db.Store.upsert_papers takes
    verify(api_key=None) -> {"ok": True}   one fresh request with a fixed public word; nothing is stored; a typed key
                                           is used instead of the saved one; raises SourceError(kind) on failure
    pdf_routes(paper) -> ordered [{kind, url, auto, needs_login, label}] this source contributes

Error kinds (SourceError.kind): auth_required, quota_exhausted, network_error, unavailable, bad_response,
invalid_input, not_found. A message is built only from the kind, an HTTP status and a sanitised provider code; provider
text and key text never reach it.
"""
import http.client
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from .sources import SourceError, source_pages

KEY_REQUIREMENTS = ("none", "optional", "required")
KINDS = ("auth_required", "quota_exhausted", "network_error", "unavailable", "bad_response", "invalid_input", "not_found")
MAX_BODY = 2 * 1024 * 1024


@dataclass(frozen=True)
class SourceInfo:
    id: str
    label: str                  # the name on the settings page
    provider: str               # who runs it
    key: str                    # "none" | "optional" | "required"
    key_benefit: str            # what a key gives (empty when there is none)
    key_url: str                # where to get one
    key_env: str                # environment variable that overrides the key file; also the line prefix in the key file
    key_pattern: str            # regular expression a key must match completely
    serves_languages: tuple     # paper languages the source is good for
    query_scripts: tuple        # scripts the source can search in: "latin", "cjk"
    daily_cap: object           # local daily cap on requests (int) or None
    provider_quota: str         # the provider's own allowance, as text
    sends: str                  # what leaves the machine, as text
    claims_id: str              # id in harness/sources.json holding the checked external facts
    key_shared_with: str = ""   # id of the source whose key (file, environment variable, format) this one uses; "" = its own


ARXIV_INFO = SourceInfo(
    id="arxiv", label="arXiv", provider="arXiv（经 OpenAlex 索引检索）", key="none",
    key_benefit="", key_url="", key_env="", key_pattern="",
    serves_languages=("en",), query_scripts=("latin",), daily_cap=None,
    provider_quota="与 OpenAlex 共用额度", sends="英文检索词与日期范围（公开元数据查询）；不含画像、笔记、论文库和私有 ID",
    claims_id="ARXIV")

OPENALEX_INFO = SourceInfo(
    id="openalex", label="期刊与会议论文", provider="OpenAlex", key="optional",
    key_benefit="免费密钥把每日额度提高约 10 倍（1000 点提高到 10000 点）",
    key_url="https://help.openalex.org/api-reference/authentication",
    key_env="OPENALEX_API_KEY", key_pattern=r"[A-Za-z0-9._~-]{8,256}",
    serves_languages=("en", "zh"), query_scripts=("latin", "cjk"), daily_cap=None,
    provider_quota="无密钥每天 1000 点（约 0.1 美元），有免费密钥每天 10000 点（约 1 美元）",
    sends="检索词、DOI 与标题（公开元数据查询）；不含画像、笔记、论文库和私有 ID",
    claims_id="OPENALEX-AUTH")


def all_infos():
    """Every registered source, in the order the settings page lists them."""
    from .baidu_scholar import BAIDU_SCHOLAR_INFO
    from .baidu_web import BAIDU_WEB_INFO
    return (ARXIV_INFO, OPENALEX_INFO, BAIDU_SCHOLAR_INFO, BAIDU_WEB_INFO)


def info(source_id):
    return next((i for i in all_infos() if i.id == source_id), None) if isinstance(source_id, str) else None


# ---------------------------------------------------------------- errors
def http_kind(status):
    """The error kind for an HTTP status."""
    if status in (401, 403):
        return "auth_required"
    if status == 429:
        return "quota_exhausted"
    if status == 404:
        return "not_found"
    if status == 400:
        return "invalid_input"
    return "unavailable" if isinstance(status, int) and status >= 500 else "bad_response"


def error_for(label, kind, status=None, code=None, secrets=()):
    """A SourceError whose message is only the kind, an HTTP status and a short sanitised provider code."""
    parts = [f"{label}: {kind}"]
    if isinstance(status, int):
        parts.append(f"HTTP {status}")
    raw = str(code if code is not None else "")
    for secret in secrets:          # a provider that echoes the key as its "code" must not leave most of it behind after cleaning
        if secret and isinstance(secret, str):
            raw = raw.replace(secret, "")
    safe = re.sub(r"[^A-Za-z0-9_.-]", "", raw)[:32]
    if safe:
        parts.append(f"code {safe}")
    text = " ".join(parts)
    for secret in secrets:
        if secret and isinstance(secret, str):
            text = text.replace(secret, "***")
    return SourceError(text, kind)


def _error_payload(exc):
    """The decoded JSON body of an HTTP error, or None (no body, not JSON, not an object). Read at most 4 KB."""
    try:
        payload = json.loads(exc.read(4096).decode("utf-8", "replace"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def fetch_json(request, label, secrets=(), timeout=20, max_bytes=MAX_BODY, on_429=None):
    """One request, no retry, no cache. Returns the parsed JSON, or raises SourceError with a kind.
    For search endpoints only: a 404 is reported as `unavailable`. A single-record lookup, where 404 means "no such
    record", must not use this helper (OpenAlex lookups use OpenAlexClient._fetch).
    `on_429(payload_or_None)` returns the kind for an HTTP 429 (a source whose 429 may be a per-second limit, not a used-up day);
    without it a 429 is quota_exhausted as before."""
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(max_bytes + 1)
    except urllib.error.HTTPError as exc:
        # A search API answering 404 has no such service for this account (measured with Baidu, 2026-10-23): unavailable,
        # not "nothing found".
        if exc.code == 429 and on_429 is not None:
            raise error_for(label, on_429(_error_payload(exc)), status=429, secrets=secrets) from None
        kind = "unavailable" if exc.code == 404 else http_kind(exc.code)
        raise error_for(label, kind, status=exc.code, secrets=secrets) from None
    except http.client.InvalidURL:
        raise error_for(label, "invalid_input", secrets=secrets) from None
    except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException):
        raise error_for(label, "network_error", secrets=secrets) from None
    if len(raw) > max_bytes:
        raise error_for(label, "bad_response", secrets=secrets)
    try:
        return json.loads(raw.decode("utf-8", "replace"))
    except ValueError:
        raise error_for(label, "bad_response", secrets=secrets) from None


# ---------------------------------------------------------------- routes
def paper_oa(paper):
    """The open-access facts of a paper dict, from `oa` (a dict) or `oa_json` (its stored text); {} when absent or broken."""
    if not isinstance(paper, dict):
        return {}
    oa = paper.get("oa")
    if oa is None:
        oa = paper.get("oa_json")
    if isinstance(oa, str):
        try:
            oa = json.loads(oa) if oa.strip() else None
        except ValueError:
            oa = None
    return oa if isinstance(oa, dict) else {}


def route(kind, url, auto, needs_login, label):
    return {"kind": kind, "url": url, "auto": bool(auto), "needs_login": bool(needs_login), "label": label}


def https_url(value):
    return value if isinstance(value, str) and value.startswith("https://") and len(value) <= 2000 else None


def openalex_routes(paper):
    """arXiv PDF, then the https PDF links OpenAlex reports (both fetched automatically), then its landing page."""
    routes, seen = [], set()
    arxiv_id = paper.get("arxiv_id") if isinstance(paper, dict) else None
    if isinstance(arxiv_id, str) and arxiv_id.strip():
        url = f"https://arxiv.org/pdf/{arxiv_id.strip()}"
        routes.append(route("arxiv_pdf", url, True, False, "arXiv"))
        seen.add(url)
    oa = paper_oa(paper)
    for url in oa.get("pdf_urls") or []:
        url = https_url(url)
        if url and url not in seen:
            seen.add(url)
            routes.append(route("oa_pdf", url, True, False, "开放获取 PDF"))
    landing = https_url(oa.get("landing_page"))
    if landing and landing not in seen:
        routes.append(route("landing", landing, False, False, "原文页面"))
    return routes


PAGE_LABELS = {"baidu_scholar": "百度学术", "baidu_web": "百度学术"}   # label of a source's own page; the reader chooses its words by kind


def _doi_url(value):
    from .reference_files import _doi
    doi = _doi(value)
    return f"https://doi.org/{doi}" if doi else None


def pdf_routes(paper):
    """Every way to the paper's file, most direct first:
    arXiv PDF (auto), OpenAlex's https PDF links (auto), [a DOI lookup of OpenAlex's facts happens in App.download_pdf],
    OpenAlex's landing page (no login), a source's own page such as Baidu Scholar's (may need a login), the publisher
    page behind the DOI (may need a login). A bare DOI is a route to a page, never a PDF source."""
    routes = openalex_routes(paper)
    seen = {r["url"] for r in routes}
    for page in source_pages(paper_oa(paper)):
        if page["url"] not in seen:
            seen.add(page["url"])
            routes.append(route("source_page", page["url"], False, True, PAGE_LABELS.get(page["source"], "来源页面")))
    publisher = _doi_url(paper.get("doi")) if isinstance(paper, dict) else None
    if publisher and publisher not in seen:
        routes.append(route("publisher_page", publisher, False, True, "出版方"))
    return routes


def paper_url(paper, doi_must_be_link=False):
    """The one link shown for a paper: arXiv, else its DOI, else OpenAlex, else the page of a source that reported it."""
    if paper.get("arxiv_id"):
        return f"https://arxiv.org/abs/{paper['arxiv_id']}"
    doi = paper.get("doi") or ""
    if doi and (not doi_must_be_link or doi.startswith("http")):
        return doi
    if paper.get("openalex_id"):
        return paper["openalex_id"]
    pages = source_pages(paper_oa(paper))
    return pages[0]["url"] if pages else None

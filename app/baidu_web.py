"""Baidu AI Search restricted to xueshu.baidu.com: a second Chinese-language paper source, used only with the user's own key.

    POST https://qianfan.baidubce.com/v2/ai_search/web_search
    Authorization: Bearer <key>
    {"messages": [{"role": "user", "content": <query>}], "search_source": "baidu_search_v2",
     "resource_type_filter": [{"type": "web", "top_k": <n>}], "search_filter": {"match": {"site": ["xueshu.baidu.com"]}},
     "search_recency_filter": "week|month|semiyear|year"   (only when the owner chose a time window)}

Why it exists: the Baidu Scholar tool (app/baidu_scholar.py) answers HTTP 404 for the owner's account, while the same Qianfan key
gets HTTP 200 from this endpoint and, with the site filter, returns recent Chinese papers (claim CH-BAIDU-WEB-SEARCH in
harness/sources.json; docs/evidence/2026-10-23-baidu-live-checks.txt). The key is therefore the SAME key as Baidu Scholar's
(SourceInfo.key_shared_with): one key file, one environment variable, one field in Settings. The owner's "每天最多 40 次" is for that one
key, so the DAILY COUNTER is shared too: both sources reserve from `source_usage:baidu_scholar:<day>` (cap 40 in total, UTC+8). Their
switch, 24 h cache (data/cache/baidu_web/) and status (`source_status:baidu_web`) are their own.

What the answer gives (real answer of 2026-10-23, tests/fixtures/baidu_web/success.json): {request_id, references[]} with, per
reference, a title (often ending in a space), the xueshu.baidu.com page, a `date` ("2026-10-19 00:00:00"; WHAT IT MEANS IS
UNVERIFIED: the real sample, asked without any time filter, has all seven dates within 16 days, so it is probably a page or index
date) and `content`: "<title> 来自 <site>  喜欢N 阅读量: N 作者: a, b 摘要: ... 关键词:
x y z  年份: 2026". Title, authors, abstract, keywords and the 年份 are taken from it; a plausible 年份 becomes the year of `published`
(YYYY-01-01) unless `date` is in the same year, in which case the full date is kept; without a 年份 the date is used as it comes. NO DOI, NO journal, NO PDF link. The authors are
parsed but not stored: the papers table has no place for them (and this change adds no migration). Patents (申请(专利)号, 发明人)
are not papers and are left out. `markdown_content`, `snippet` and every other field are never stored and never cached.

The error shape is unknown: a non-200 status is classified by fetch_json; a 200 body with a `code`/`message` (or `error`) and no
`references` is classified by its message text like Baidu Scholar's; `references` that is not a list is `bad_response`.
Quota: Baidu says 1500 free calls a month (about 50 a day) and billing after that (UNVERIFIED for this account); the local cap is
40 a day for both Baidu sources together, reserved atomically BEFORE each request, a failed request still counts, nothing is retried.
An HTTP 429 is a per-second limit (transient, `unavailable`) unless its body names the daily allowance.
"""
import datetime
import hashlib
import json
import re
import urllib.parse
import urllib.request

from . import baidu_scholar
from .baidu_scholar import API_HOST, DAILY_CAP, UA, BaiduScholar, _classify
from .baidu_scholar import _collapse
from .source_adapters import SourceInfo, error_for, paper_oa, route
from .sources import SourceError, page_url

LABEL = "Baidu Web"
SOURCE_ID = "baidu_web"
API = f"https://{API_HOST}/v2/ai_search/web_search"
SITE = "xueshu.baidu.com"
MAX_UNITS = 72                  # the documented limit of the query text; a Chinese character counts 2
MAX_TOP_K = 50                  # the documented limit of results per resource type
RECENCY = ("week", "month", "semiyear", "year")
VERIFY_WORD = "知识图谱"         # fixed public word for the settings page's test button
VERIFY_TOP_K = 3
MIN_ABSTRACT = 40               # without a 摘要 marker the remaining text is an abstract only if it is at least this long
USAGE_PREFIX = baidu_scholar.USAGE_PREFIX      # ONE daily counter for the one Qianfan key (owner: 每天最多 40 次)
STATUS_KEY = f"source_status:{SOURCE_ID}"

BAIDU_WEB_INFO = SourceInfo(
    id=SOURCE_ID, label="百度搜索", provider="百度千帆（百度 AI 搜索）", key="required",
    key_benefit="与百度学术共用同一个千帆密钥；没有密钥无法检索",
    key_url="https://console.bce.baidu.com/qianfan/ais/console/apiKey",      # UNVERIFIED address of the Qianfan API key page
    key_env="BAIDU_SCHOLAR_API_KEY", key_pattern=r"[A-Za-z0-9._~+/=:-]{8,512}",
    serves_languages=("zh",), query_scripts=("cjk",), daily_cap=DAILY_CAP,
    provider_quota="百度 AI 搜索免费每月 1500 次（约每天 50 次），之后按量计费（未验证）；限定站点是“限时免费”功能。本地每天最多 40 次（与百度学术合计），日界按北京时间（未验证）",
    sends="含中文的项目关键词、创建项目时的检索词、种子论文标题检索（用你自己的密钥，限定百度学术站点）；不含画像、笔记、论文库和私有 ID",
    claims_id="CH-BAIDU-WEB-SEARCH", key_shared_with="baidu_scholar")

_MARKER = re.compile(r"(作者|摘要|关键词|年份)\s*[:\uff1a]")
_NOISE = re.compile(r"(?:来自\s*\S+\s*)?喜欢\s*\d+\s*阅读量\s*[:\uff1a]\s*\d+")
_ORDER = {"作者": 0, "摘要": 1, "关键词": 2, "年份": 3}       # a marker counts only at its first occurrence and only in this order
_YEAR = re.compile(r"\s*(\d{4})(?!\d)")
_PATENT = re.compile(r"申请\s*[\(（]\s*专利\s*[\)）]\s*号|发明人\s*[:\uff1a]")
_AUTHOR_SPLIT = re.compile(r"[,，;；、]")
_KEYWORD_SPLIT = re.compile(r"[\s,，;；、]+")
_ID = re.compile(r"[A-Za-z0-9_.:-]{1,100}")
_DATE = re.compile(r"(\d{4}-\d{2}-\d{2})(?:[\sT]|$)")


def query_units(text):
    """The length of `text` as the API counts it, conservatively: every non-ASCII character (Chinese, curly quotes, ellipsis,
    dashes) is 2, an ASCII one 1."""
    return sum(2 if ord(ch) > 127 else 1 for ch in str(text or ""))


def clean_query(text):
    """The query as sent: control characters become spaces, whitespace collapses, and the text is cut to MAX_UNITS."""
    if not isinstance(text, str):
        return ""
    text = re.sub(r"\s+", " ", re.sub("[\x00-\x1f\x7f\u2028\u2029]", " ", re.sub("[\ud800-\udfff]", "", text))).strip()
    out, units = [], 0
    for ch in text:
        width = query_units(ch)
        if units + width > MAX_UNITS:
            break
        out.append(ch)
        units += width
    return "".join(out).strip()


def request_body(text, top_k, recency=None):
    """The JSON body (UTF-8 bytes): web results only, on the xueshu.baidu.com site, and a recency filter only when one is given."""
    body = {"messages": [{"role": "user", "content": text}], "search_source": "baidu_search_v2",
            "resource_type_filter": [{"type": "web", "top_k": int(top_k)}], "search_filter": {"match": {"site": [SITE]}}}
    if recency in RECENCY:
        body["search_recency_filter"] = recency
    return json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def request_for(data, key, url=API):
    """The POST request. The key is an unredirected header, only for the Qianfan host over https: a redirect cannot carry it
    elsewhere and it is never part of a URL, a body, a cache name or an error."""
    request = urllib.request.Request(url, data=data, method="POST", headers={
        "User-Agent": UA, "Accept": "application/json", "Content-Type": "application/json"})
    parts = urllib.parse.urlsplit(url)
    if key and parts.scheme == "https" and parts.hostname == API_HOST:
        request.add_unredirected_header("Authorization", f"Bearer {key}")
    return request


def _text(value):
    """`value` if it is a string, else "" (a dict or a number is never turned into text with str())."""
    return value if isinstance(value, str) else ""


def title_mark(text):
    """A title as compared for duplicates between the Baidu sources: case, spaces and punctuation ignored (Chinese titles differ
    in exactly these between the two answers)."""
    return re.sub(r"[\W_]+", "", str(text or "").lower(), flags=re.UNICODE)


def _page_url(value, upgrade=True):
    """An https page on xueshu.baidu.com, else None (see sources.page_url)."""
    return page_url(_collapse(_text(value)), SITE, upgrade=upgrade)


def _date(value):
    """YYYY-MM-DD from the answer's `date`, else None. The day is kept; what the date means is unverified."""
    match = _DATE.match(value.strip()) if isinstance(value, str) else None
    if not match:
        return None
    try:
        day = datetime.date.fromisoformat(match.group(1))
    except ValueError:
        return None
    return day.isoformat() if 1000 <= day.year <= 2999 else None


def _plausible_year(text):
    match = _YEAR.match(text or "")
    year = int(match.group(1)) if match else None
    return year if year is not None and 1900 <= year <= datetime.date.today().year + 1 else None


def parse_content(content, title=""):
    """Split a reference's `content` into authors, abstract, keywords and year; the title, the site and the 喜欢/阅读量 counters are
    noise. {"authors": [...], "abstract": str, "keywords": [...], "year": int|None, "patent": bool}. A marker (作者, 摘要, 关键词,
    年份) counts only at its first occurrence and only after the markers before it, so "通讯作者：" inside an abstract stays text.
    Without a 摘要 marker the text before the first marker is the abstract only when it is at least MIN_ABSTRACT characters long."""
    text = _collapse(_text(content))
    shown = _collapse(_text(title))
    if shown and text.startswith(shown):
        text = text[len(shown):]
    text = _collapse(_NOISE.sub(" ", text))
    if _PATENT.search(text):
        return {"authors": [], "abstract": "", "keywords": [], "year": None, "patent": True}
    marks, seen, last = [], set(), -1
    for mark in _MARKER.finditer(text):
        name = mark.group(1)
        if name in seen or _ORDER[name] < last:
            continue
        seen.add(name)
        last = _ORDER[name]
        marks.append(mark)
    lead = text[:marks[0].start()].strip() if marks else text
    parts = {}
    for i, mark in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        parts[mark.group(1)] = text[mark.end():end].strip()
    authors = [a[:80] for a in (_collapse(x) for x in _AUTHOR_SPLIT.split(parts.get("作者", ""))) if a][:50]
    keywords = [k[:80] for k in _KEYWORD_SPLIT.split(parts.get("关键词", "")) if k][:20]
    abstract = parts["摘要"] if "摘要" in parts else (lead if len(lead) >= MIN_ABSTRACT else "")
    return {"authors": authors, "abstract": abstract[:10000], "keywords": keywords, "year": _plausible_year(parts.get("年份")), "patent": False}


def parse_search(payload, secrets=()):
    """Papers (db.Store.upsert_papers shape) from a decoded response, or a SourceError with a kind. `secrets` (the key) are removed
    from anything the provider's code or message could put into the error."""
    if not isinstance(payload, dict):
        raise error_for(LABEL, "bad_response")
    code, message = payload.get("code"), payload.get("message")
    if code is None and isinstance(payload.get("error"), dict):
        code, message = payload["error"].get("code") or payload["error"].get("type") or "error", payload["error"].get("message")
    if code is None and payload.get("error_code") is not None:
        code, message = payload["error_code"], payload.get("error_msg")
    if code is not None and str(code).strip() not in ("0", ""):
        raise error_for(LABEL, _classify(code, message), code=code, secrets=secrets)
    references = payload.get("references")
    if not isinstance(references, list):
        raise error_for(LABEL, "bad_response")
    papers = []
    for item in references:
        paper = _paper(item) if isinstance(item, dict) else None
        if paper:
            papers.append(paper)
    return papers


def _paper(item):
    title = _collapse(_text(item.get("title")))[:500]
    if not title:
        return None
    parsed = parse_content(item.get("content"), title)
    if parsed["patent"]:
        return None
    page = _page_url(item.get("url"))
    paper_id = ""
    if page:
        found = urllib.parse.parse_qs(urllib.parse.urlsplit(page).query).get("paperid") or [""]
        paper_id = _collapse(found[0])[:120]
    if paper_id and _ID.fullmatch(paper_id):
        key = f"baidu:{paper_id}"
    else:      # no id, or one with characters a seed identifier could not carry: a stable hash of what there is
        key = "baidu:t-" + hashlib.sha1((paper_id or title.casefold()).encode("utf-8")).hexdigest()[:16]
    keywords = parsed["keywords"]
    published, year = _date(item.get("date")), parsed["year"]
    if year and not (published and int(published[:4]) == year):
        published = f"{year:04d}-01-01"     # the date is probably a page or index date (unverified): a plausible 年份 is the year
    return {
        "key": key, "openalex_id": None, "doi": None, "arxiv_id": None,
        "title": title, "abstract": parsed["abstract"], "published": published,
        "source": None, "topic": keywords[0] if keywords else None,
        "authors": [],          # parsed (parse_content) but not stored: the papers table has no place for them
        "group_name": "field",
        # `via` is always there, also without a page: it is what makes the web switch govern the paper (user_settings.SourcePolicy).
        "oa": {"pages": [{"source": SOURCE_ID, "url": page}] if page else [], "via": [SOURCE_ID]},
        # No metadata_language key at all: Baidu does not report a language and a stored one must not be overwritten.
    }


def slim_payload(payload):
    """What is cached: per reference only the page, title, date and content. markdown_content, snippet and the rest are dropped."""
    refs = payload.get("references") if isinstance(payload, dict) else None
    return {"references": [{k: ref[k] for k in ("url", "title", "date", "content") if k in ref}
                           for ref in (refs if isinstance(refs, list) else [])[:MAX_TOP_K] if isinstance(ref, dict)]}


class BaiduWeb(BaiduScholar):
    """Same provider, key, counter mechanism and cache as BaiduScholar; another endpoint (POST) and another parser."""
    info = BAIDU_WEB_INFO
    label = LABEL
    usage_prefix = USAGE_PREFIX
    status_key = STATUS_KEY

    @staticmethod
    def _parse(payload):
        return parse_search(payload)

    def _request(self, body, api_key=None):
        return request_for(body.encode("utf-8"), api_key or self.api_key)

    # ---------------------------------------------------------------- interface
    def search(self, query, since=None, page=1, per_page=10, recency=None):
        """Web results on xueshu.baidu.com for `query`: `per_page` (1..50) is top_k, `recency` one of RECENCY or None. The API
        has no pages, so a second page is empty and costs nothing. `since` drops papers dated before its year (unknown dates stay)."""
        text = clean_query(query)
        if not text:
            raise error_for(self.label, "invalid_input")
        try:
            if int(page) > 1:
                return []
        except (TypeError, ValueError):
            pass
        try:
            limit = max(1, min(int(per_page), MAX_TOP_K))
        except (TypeError, ValueError):
            limit = 10
        body = request_body(text, limit, recency).decode("utf-8")
        papers = self._read_cache(body)
        if papers is None:
            if not self.api_key:
                raise error_for(self.label, "auth_required")
            try:
                self._reserve()
                payload = self._live(body, self.api_key)
                papers = parse_search(payload, secrets=(self.api_key,))
            except SourceError as exc:
                self._note_status(exc.kind)
                raise
            self._write_cache(body, slim_payload(payload))
            self._note_status("ok")
        floor = int(str(since)[:4]) if since and str(since)[:4].isdigit() else None
        if floor:
            papers = [p for p in papers if not p["published"] or int(p["published"][:4]) >= floor]
        return papers[:limit]

    def verify(self, api_key=None):
        """One fresh request with a fixed public word. The typed key wins over the saved one. The call is counted against the
        daily allowance, nothing is cached and no paper is stored."""
        key = api_key or self.api_key
        if not key:
            raise error_for(self.label, "auth_required")
        self._reserve()
        parse_search(self._live(request_body(VERIFY_WORD, VERIFY_TOP_K).decode("utf-8"), key), secrets=(key, self.api_key))
        return {"ok": True}

    def pdf_routes(self, paper):
        """No PDF. The xueshu.baidu.com page counts as a source that may need a login: shown to the user, never fetched."""
        routes, seen = [], set()
        for page in paper_oa(paper).get("pages") or []:
            url = _page_url(page.get("url"), upgrade=False) if isinstance(page, dict) and page.get("source") == SOURCE_ID else None
            if url and url not in seen:
                seen.add(url)
                routes.append(route("source_page", url, False, True, "百度学术"))
        return routes

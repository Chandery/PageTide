"""Baidu Scholar search through the Qianfan API: a Chinese-language paper source, used only with the user's own key.

    GET https://qianfan.baidubce.com/v2/tools/baidu_scholar/search?wd=<keyword>&pageNum=<n>
    Authorization: Bearer <key>

EVERY FIELD NAME BELOW IS UNVERIFIED. The shape comes from Baidu's documentation page (read 2026-10-02, claim
CH-BAIDU-SCHOLAR in harness/sources.json); no real call has ever been made from this app. Parsing is therefore
tolerant: a list or a scalar, a missing field and an unknown field are all handled, and a surprise becomes a
`bad_response`, never a crash. Run tools/source_smoke.py with a real key to check the shape.

What the API gives: title, original abstract, DOI, keywords, year, journal and a Baidu Scholar page. It gives NO authors,
NO citation counts, NO PDF link and NO exact date, and it has no date sort. Free allowance: about 50 calls a day, so the
local cap is 40; the day changes at 00:00 UTC+8 (unverified). The AI summary (`aiAbstract`) is model text, not the
paper's abstract: it is never requested, never stored and dropped from anything cached (AGENTS rule 7).

Where the pieces live: the key in its 0600 file (source_keys), sent only as an unredirected header to the Qianfan host;
the day's call counter in the `settings` table (`source_usage:baidu_scholar:<day>`), reserved atomically BEFORE each
request, so the "clear downloaded paper information" button (which empties the cache folder) cannot reset it; answers in
data/cache/baidu_scholar/ for 24 hours, named by a hash of the URL (which holds no key) and answered without spending a call.
A failed request still counts (the provider may count it) and is never retried.
"""
import contextlib
import datetime
import hashlib
import json
import os
import re
import sqlite3
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

from . import source_adapters
from .source_adapters import SourceInfo, error_for, fetch_json, paper_oa, route
from .sources import SOURCE_PAGE_DOMAINS, SourceError, page_url, source_pages

LABEL = "Baidu Scholar"
API_HOST = "qianfan.baidubce.com"
API = f"https://{API_HOST}/v2/tools/baidu_scholar/search"
UA = "PaperDigHelper/0.1 (local research; read-only metadata)"
DAILY_CAP = 40                  # free plan: about 50 calls a day, more needs a support ticket
CACHE_TTL_SECONDS = 24 * 3600
GAP_SECONDS = 1.0               # a polite pause between live requests (the provider's rate limit is unknown)
MAX_QUERY = 100
VERIFY_WORD = "知识图谱"         # fixed public word for the settings page's test button
SOURCE_ID = "baidu_scholar"
USAGE_PREFIX = f"source_usage:{SOURCE_ID}:"
STATUS_KEY = f"source_status:{SOURCE_ID}"
KEEP_DAYS = 7
UTC_PLUS_8 = datetime.timedelta(hours=8)

BAIDU_SCHOLAR_INFO = SourceInfo(
    id=SOURCE_ID, label="百度学术", provider="百度学术（百度千帆 API）", key="required",
    key_benefit="没有密钥无法检索；用你自己的千帆密钥访问百度学术，免费每天约 50 次",
    key_url="https://console.bce.baidu.com/qianfan/ais/console/apiKey",      # UNVERIFIED address of the Qianfan API key page
    key_env="BAIDU_SCHOLAR_API_KEY", key_pattern=r"[A-Za-z0-9._~+/=:-]{8,512}",   # a '/' is allowed (the format is unverified)
    serves_languages=("zh", "en"), query_scripts=("cjk", "latin"), daily_cap=DAILY_CAP,
    provider_quota="免费每天约 50 次；超出需向百度提工单（未验证）。本地每天最多 40 次（与百度搜索合计），日界按北京时间（未验证）",
    sends="含中文的项目关键词、创建项目时的检索词、种子论文标题检索（用你自己的密钥）；不含画像、笔记、论文库和私有 ID",
    claims_id="CH-BAIDU-SCHOLAR")

# A per-second limit (QPS, rate limit, 频率, 限流) is transient: the next minute works. A used-up allowance (quota, daily, limit/exceed
# without a rate word, 额度, 次数, 超出) lasts until the day changes. Latin words are matched as whole words ("regenerate" is not "rate");
# "_" is no boundary here because the provider's codes look like RATE_LIMIT_QPS.
_QPS = re.compile(r"(?<![A-Za-z])qps(?![A-Za-z])|(?<![A-Za-z])rate[\s_-]*limit|too many requests|(?<![A-Za-z])rate(?![A-Za-z])|频率|限流|并发", re.I)
_QUOTA = re.compile(r"(?<![A-Za-z])(?:quota|daily|exceed\w*|limit\w*)(?![A-Za-z])|额度|次数|超出", re.I)
_AUTH = re.compile(r"auth|token|key|permission|credential|forbidden|unauthori|鉴权|认证|权限|授权|签名|密钥", re.I)
_KEYWORD_SPLIT = re.compile(r"[;；,，、\n]")
_pace_lock = threading.Lock()
_last_request = [0.0]


def _collapse(value):
    return re.sub(r"\s+", " ", str(value if value is not None else "")).strip()


def clean_query(text):
    """The query as sent: control characters become spaces, whitespace collapses, at most MAX_QUERY characters."""
    if not isinstance(text, str):
        return ""
    return re.sub(r"\s+", " ", re.sub("[\x00-\x1f\x7f\u2028\u2029]", " ", re.sub("[\ud800-\udfff]", "", text))).strip()[:MAX_QUERY].strip()


def _page_url(value, upgrade=True):
    """An https page on baidu.com (or a subdomain), else None (see sources.page_url)."""
    return page_url(_collapse(value), SOURCE_PAGE_DOMAINS[SOURCE_ID], upgrade=upgrade)


def _year(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, str) and value.strip().isdigit():
        value = int(value.strip())
    return value if isinstance(value, int) and 1000 <= value <= 2999 else None


def _keywords(value):
    items = value if isinstance(value, list) else _KEYWORD_SPLIT.split(str(value or ""))
    return [k[:80] for k in (_collapse(x) for x in items) if k][:20]


def _doi(value):
    from .reference_files import _doi as normalise
    return normalise(value)


def strip_ai_abstract(value, depth=0):
    """The value without any AI summary field, at any depth (the model's text is not the paper's abstract); what gets cached."""
    if depth > 8:
        return None
    if isinstance(value, dict):
        return {k: strip_ai_abstract(v, depth + 1) for k, v in value.items() if "aiabstract" not in str(k).lower().replace("_", "")}
    if isinstance(value, list):
        return [strip_ai_abstract(v, depth + 1) for v in value]
    return value


def _classify(code, message):
    text = f"{code} {message}"
    if _QPS.search(text):
        return "unavailable"
    if _QUOTA.search(text):
        return "quota_exhausted"
    return "auth_required" if _AUTH.search(text) else "unavailable"


def kind_for_429(payload):
    """An HTTP 429 is a per-second limit (transient, "unavailable") unless its body names the daily allowance."""
    if isinstance(payload, dict):
        code, message = payload.get("code"), payload.get("message")
        if code is None and isinstance(payload.get("error"), dict):
            code, message = payload["error"].get("code") or payload["error"].get("type"), payload["error"].get("message")
        if _classify(code, message) == "quota_exhausted":
            return "quota_exhausted"
    return "unavailable"


def parse_search(payload, secrets=()):
    """Papers (db.Store.upsert_papers shape) from a decoded response, or a SourceError with a kind. `secrets` (the key) are removed
    from anything the provider's code or message could put into the error."""
    if not isinstance(payload, dict):
        raise error_for(LABEL, "bad_response")
    code, message = payload.get("code"), payload.get("message")
    if code is None and isinstance(payload.get("error"), dict):
        code, message = payload["error"].get("code") or payload["error"].get("type") or "error", payload["error"].get("message")
    if code is None:
        raise error_for(LABEL, "bad_response")
    if str(code).strip() != "0":
        raise error_for(LABEL, _classify(code, message), code=code, secrets=secrets)
    items = payload.get("data")
    if items is None:
        return []
    if not isinstance(items, list):
        raise error_for(LABEL, "bad_response")
    papers = []
    for item in items:
        paper = _paper(item) if isinstance(item, dict) else None
        if paper:
            papers.append(paper)
    return papers


def _paper(item):
    title = _collapse(item.get("title"))[:500]
    if not title:
        return None
    doi = _doi(item.get("doi"))
    paper_id = _collapse(item.get("paperId"))[:120]
    if doi:
        key = f"https://doi.org/{doi}"
    elif paper_id and re.fullmatch(r"[A-Za-z0-9_.:-]{1,100}", paper_id):
        key = f"baidu:{paper_id}"
    else:      # no id, or one with characters a seed identifier could not carry: a stable hash of what there is
        key = "baidu:t-" + hashlib.sha1((paper_id or title.casefold()).encode("utf-8")).hexdigest()[:16]
    year = _year(item.get("publishYear"))
    info = item.get("publishInfo")
    journal = _collapse(info.get("journalName") if isinstance(info, dict) else None)[:200]
    keywords = _keywords(item.get("keyword"))
    page = _page_url(item.get("url"))
    return {
        "key": key, "openalex_id": None, "doi": f"https://doi.org/{doi}" if doi else None, "arxiv_id": None,
        "title": title, "abstract": _collapse(item.get("abstract"))[:10000], "published": f"{year:04d}-01-01" if year else None,
        "source": journal or None, "topic": keywords[0] if keywords else None, "authors": [], "group_name": "field",
        "oa": {"pages": [{"source": SOURCE_ID, "url": page}], "via": [SOURCE_ID]} if page else None,
        # No metadata_language key at all: Baidu does not report a language and a stored one must not be overwritten.
    }


def request_for(url, key):
    """The request for a Qianfan URL. The key is an unredirected header, only for the Qianfan host over https: a redirect
    cannot carry it elsewhere and it is never part of a URL, a cache name or an error."""
    request = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    parts = urllib.parse.urlsplit(url)
    if key and parts.scheme == "https" and parts.hostname == API_HOST:
        request.add_unredirected_header("Authorization", f"Bearer {key}")
    return request


class BaiduScholar:
    info = BAIDU_SCHOLAR_INFO
    # What a subclass (baidu_web.BaiduWeb: the same provider, key, quota mechanism and cache, another endpoint) changes.
    label = LABEL
    usage_prefix = USAGE_PREFIX
    status_key = STATUS_KEY

    def __init__(self, cache_dir, db_path, api_key=None, daily_cap=DAILY_CAP, now=None):
        self.cache = Path(cache_dir)          # created on the first write, never for a source that is not used
        self.db_path = Path(db_path)
        self.api_key = api_key
        self.daily_cap = daily_cap
        self.now = now or (lambda: datetime.datetime.now(datetime.timezone.utc))

    # ---------------------------------------------------------------- request
    def _request(self, url, api_key=None):
        return request_for(url, api_key or self.api_key)

    @staticmethod
    def _url(text, page_number):
        return f"{API}?{urllib.parse.urlencode({'wd': text, 'pageNum': page_number})}"

    def _live(self, url, key):
        """The one place a request leaves. Quota is reserved by the caller first."""
        with _pace_lock:
            wait = GAP_SECONDS - (time.monotonic() - _last_request[0])
            if wait > 0:
                time.sleep(wait)
            _last_request[0] = time.monotonic()
        return fetch_json(self._request(url, api_key=key), self.label, secrets=(key, self.api_key), timeout=20, on_429=kind_for_429)

    # ---------------------------------------------------------------- interface
    def search(self, query, since=None, page=1, per_page=10):
        text = clean_query(query)
        if not text:
            raise error_for(self.label, "invalid_input")
        try:
            page_number = max(int(page), 1) - 1
        except (TypeError, ValueError):
            page_number = 0
        try:
            limit = max(1, min(int(per_page), 50))
        except (TypeError, ValueError):
            limit = 10
        url = self._url(text, page_number)
        papers = self._read_cache(url)
        if papers is None:
            if not self.api_key:
                raise error_for(self.label, "auth_required")
            try:
                self._reserve()
                payload = self._live(url, self.api_key)
                papers = parse_search(payload, secrets=(self.api_key,))
            except SourceError as exc:
                self._note_status(exc.kind)
                raise
            self._write_cache(url, strip_ai_abstract(payload))
            self._note_status("ok")
        floor = int(str(since)[:4]) if since and str(since)[:4].isdigit() else None
        if floor:
            papers = [p for p in papers if not p["published"] or int(p["published"][:4]) >= floor]
        return papers[:limit]

    def verify(self, api_key=None):
        """One fresh request with a fixed public word. The typed key wins over the saved one. The call is counted
        against the daily allowance (it spends one of the provider's), nothing is cached and no paper is stored."""
        key = api_key or self.api_key
        if not key:
            raise error_for(self.label, "auth_required")
        self._reserve()
        parse_search(self._live(self._url(VERIFY_WORD, 0), key), secrets=(key, self.api_key))
        return {"ok": True}

    def pdf_routes(self, paper):
        """Baidu has no PDF. Its page counts as a source that may need a login: shown to the user, never fetched."""
        routes, seen = [], set()
        for page in paper_oa(paper).get("pages") or []:
            url = _page_url(page.get("url"), upgrade=False) if isinstance(page, dict) and page.get("source") == SOURCE_ID else None
            if url and url not in seen:
                seen.add(url)
                routes.append(route("source_page", url, False, True, "百度学术"))
        return routes

    # ---------------------------------------------------------------- cache
    @staticmethod
    def _parse(payload):
        return parse_search(payload)

    def _cache_path(self, url):
        return self.cache / f"{hashlib.sha256(url.encode()).hexdigest()[:16]}.json"

    def _read_cache(self, url):
        path = self._cache_path(url)
        try:
            if time.time() - path.stat().st_mtime > CACHE_TTL_SECONDS or path.stat().st_mtime > time.time() + 60:
                return None
            return self._parse(json.loads(path.read_text(encoding="utf-8")))
        except FileNotFoundError:
            return None
        except (OSError, ValueError, SourceError):
            with contextlib.suppress(OSError):
                path.unlink()      # a corrupt copy is refetched, not trusted
            return None

    def _write_cache(self, url, payload):
        path = self._cache_path(url)
        try:
            self.cache.mkdir(parents=True, exist_ok=True)
            staged = path.with_name(path.name + ".tmp")
            staged.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            os.replace(staged, path)
        except OSError:
            pass          # a cache that cannot be written only costs a later call

    # ---------------------------------------------------------------- daily counter and status (settings table)
    def _connect(self):
        conn = sqlite3.connect(str(self.db_path), timeout=30)
        conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        return conn

    def _day(self):
        return (self.now().astimezone(datetime.timezone.utc) + UTC_PLUS_8).date()

    def usage_today(self):
        with contextlib.closing(self._connect()) as conn:
            row = conn.execute("SELECT value FROM settings WHERE key=?", (self.usage_prefix + self._day().isoformat(),)).fetchone()
        try:
            return int(row[0]) if row else 0
        except (TypeError, ValueError):
            return 0

    def _reserve(self):
        """Count one call BEFORE it is made. One statement does the check and the increment, so two connections (even two
        processes) can never reserve more than the cap; no row changed means the cap is reached and no request is made."""
        day = self._day()
        cutoff = self.usage_prefix + (day - datetime.timedelta(days=KEEP_DAYS)).isoformat()
        try:
            with contextlib.closing(self._connect()) as conn, conn:
                conn.execute("DELETE FROM settings WHERE key LIKE ? AND key < ?", (self.usage_prefix + "%", cutoff))
                changed = conn.execute(
                    "INSERT INTO settings(key,value) VALUES(:k,'1') ON CONFLICT(key) DO UPDATE SET "
                    "value=CAST(value AS INTEGER)+1 WHERE CAST(value AS INTEGER) < :cap",
                    {"k": self.usage_prefix + day.isoformat(), "cap": int(self.daily_cap)}).rowcount
        except sqlite3.Error:
            raise error_for(self.label, "unavailable") from None      # no record of the count: do not call
        if changed < 1:
            raise error_for(self.label, "quota_exhausted")

    def _note_status(self, kind):
        """The last outcome of a live request: a kind and a time, nothing else."""
        value = json.dumps({"kind": kind, "at": datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()})
        with contextlib.suppress(sqlite3.Error):
            with contextlib.closing(self._connect()) as conn, conn:
                conn.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                             (self.status_key, value))

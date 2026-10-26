"""知网 (CNKI): Chinese journal articles and theses, searched in the desktop app's own CNKI window (ADR 0045).

CNKI has no public interface and sends every plain HTTP client to a puzzle a person must slide, so this server never
contacts CNKI. The desktop shell keeps a hidden CNKI window; the main page asks this module what to search (`plan`), has the
window search and open the detail pages (full abstract after its "更多" link), and posts what the window read back here.

Everything that comes back is untrusted page text: `paper_from_item` keeps only fields it can validate, caps every length,
accepts a page link only on https://kns.cnki.net and builds the key from CNKI's own database code and file name
(`cnki:<dbname>:<filename>`), never from the encrypted link. Authors, journal and keywords beyond the first are not stored
(the papers table has no place for them; no migration). DOIs are kept but not sent anywhere (owner, 2026-10-26).
"""
import re

from .reference_files import _doi
from .source_adapters import SourceInfo
from .sources import SourceError, page_url

SOURCE_ID = "cnki"
HOST = "kns.cnki.net"

KEYWORDS = 3                 # Chinese keywords searched per project and refresh (owner, 2026-10-26, same as Baidu)
MAX_NEW_PER_REFRESH = 100    # new papers per project and refresh (owner, 2026-10-26)
GUIDANCE_PER_QUERY = 10      # candidates per creation query (each needs its detail page for the abstract)
SEED_PER_QUERY = 8           # seed-search hits (result rows only; the chosen one gets its detail page)
MAX_ITEMS = 120              # items one request may carry
KNOWN_LIMIT = 5000           # CNKI ids handed to the window so it skips detail pages it already read

# What the CNKI window reports when a step fails (the shell and page use the same words), plus the shared source kinds.
PROBLEMS = ("verification_needed", "unavailable", "network_error", "desktop_only", "bad_response", "busy")

_DBNAME = re.compile(r"[A-Z]{2,8}")
_FILENAME = re.compile(r"[A-Za-z0-9_.-]{1,64}")
_KEY = re.compile(r"cnki:([A-Z]{2,8}):([A-Za-z0-9_.-]{1,64})")
_DATE = re.compile(r"(\d{4})(?:-(\d{1,2})(?:-(\d{1,2}))?)?")
_SPACE = re.compile(r"\s+")
_CUT = re.compile(r"\s*(?:\.{3,}|…+)\s*$")         # how CNKI ends a cut abstract ("..." on results pages, "......" on details)

CNKI_INFO = SourceInfo(
    id=SOURCE_ID, label="知网", provider="中国知网（在应用内的知网窗口里检索）", key="none",
    key_benefit="", key_url="", key_env="", key_pattern="",
    serves_languages=("zh",), query_scripts=("cjk",), daily_cap=None,
    provider_quota="没有公开接口；第一次检索要在知网窗口里滑一次拼图，之后按会话放行（能保持多久未验证）",
    sends="含汉字的项目关键词（每个项目每次刷新最多 3 个）、勾选中文后的创建检索式和键入的中文种子标题，在应用内的知网窗口里检索并打开详情页；不含画像、笔记、论文库和私有 ID",
    claims_id="CH-CNKI-WINDOW")


def _text(value, limit):
    return _SPACE.sub(" ", value).strip()[:limit] if isinstance(value, str) else ""


def _date(value):
    """YYYY-MM-DD from CNKI's date column ("2026-10-20", "2026-10-20 14:33", "2026-10", "2026"), else None."""
    match = _DATE.match(_text(value, 40))
    if not match:
        return None
    year, month, day = int(match.group(1)), int(match.group(2) or 1), int(match.group(3) or 1)
    if not (1900 <= year <= 2100 and 1 <= month <= 12 and 1 <= day <= 31):
        return None
    return f"{year:04d}-{month:02d}-{day:02d}"


def page(value):
    """A CNKI page link that is safe to store and show: https on kns.cnki.net only (see sources.page_url)."""
    return page_url(_text(value, 2000), HOST)


def key_of(dbname, filename):
    dbname, filename = _text(dbname, 200).upper(), _text(filename, 200)       # validated whole, never cut to fit
    if not _DBNAME.fullmatch(dbname) or not _FILENAME.fullmatch(filename):
        return None
    return f"cnki:{dbname}:{filename}"


def is_key(value):
    return isinstance(value, str) and bool(_KEY.fullmatch(value))


def paper_from_item(item, group="field"):
    """One paper in upsert_papers shape from one item the CNKI window read, or None when it lacks a valid id or a title.

    Expected fields (all optional except dbname, filename and title): url, abstract, keywords (list), date, doi. Anything
    else is ignored. The abstract is CNKI's own text, never generated."""
    if not isinstance(item, dict):
        return None
    key = key_of(item.get("dbname"), item.get("filename"))
    title = _text(item.get("title"), 500)
    if not key or not title:
        return None
    keywords = [k for k in (_text(k, 60).rstrip(";；") for k in (item.get("keywords") or [])[:12] if isinstance(k, str)) if k] \
        if isinstance(item.get("keywords"), list) else []
    link = page(item.get("url"))
    abstract = _text(item.get("abstract"), 8000)
    partial = item.get("abstract_partial") is True or bool(_CUT.search(abstract))
    abstract = _CUT.sub("", abstract).strip() or None
    return {
        "key": key, "openalex_id": None, "doi": _doi(item.get("doi")), "arxiv_id": None,
        "title": title, "abstract": abstract, "published": _date(item.get("date")),
        "source": None, "topic": keywords[0] if keywords else None,
        "authors": [],          # not stored: the papers table has no place for them
        "group_name": group,
        # `via` is always there, also without a page: it is what makes the CNKI switch govern the paper (SourcePolicy).
        # `abstract_partial`: the abstract is CNKI's snippet from a results page (cut, without the "..."); the full one is read
        # from the detail page when the person opens the paper (App.cnki_abstract).
        "oa": {"pages": [{"source": SOURCE_ID, "url": link}] if link else [], "via": [SOURCE_ID],
               "abstract_partial": bool(abstract and partial)},
        # No metadata_language key: CNKI reports none, and a stored one must not be overwritten.
    }


def papers_from_items(items, group="field"):
    """The valid, distinct papers among at most MAX_ITEMS items (a later duplicate key only adds nothing)."""
    if not isinstance(items, list):
        raise ValueError("知网结果格式无效")
    out, seen = [], set()
    for item in items[:MAX_ITEMS]:
        paper = paper_from_item(item, group)
        if paper and paper["key"] not in seen:
            seen.add(paper["key"])
            out.append(paper)
    return out


def problem_of(value):
    """The failure kind the page reported for the CNKI part, or None. Anything unknown counts as unavailable."""
    if value in (None, ""):
        return None
    return value if value in PROBLEMS else "unavailable"


def known_ids(store, limit=KNOWN_LIMIT):
    """`<dbname>:<filename>` of the CNKI papers already in the library, newest first: the window skips their detail pages."""
    rows = store.conn.execute("SELECT key FROM papers WHERE key LIKE 'cnki:%' ORDER BY created_at DESC LIMIT ?", (limit,))
    return [row[0][len("cnki:"):] for row in rows if is_key(row[0])]


class Cnki:
    """The source adapter entry for the registry and PDF routes. It cannot search from the server (see the module docstring)."""

    @property
    def info(self):
        return CNKI_INFO

    api_key = None

    def search(self, query, since=None, page=1, per_page=10):
        raise SourceError("知网只能在桌面应用的知网窗口里检索", "unavailable")

    def verify(self, api_key=None):
        raise SourceError("知网不需要密钥", "invalid_input")

    def pdf_routes(self, paper):
        from .source_adapters import pdf_routes
        return pdf_routes(paper)

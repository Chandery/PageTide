"""Project-creation helpers: seed identifiers, paper-name search, imported PDFs, AI degrade reasons.

Everything here is deterministic and offline except the OpenAlex lookups, which send only a public
identifier or an explicit user-typed title. No model is called from this module.
"""
import hashlib
import re
import shutil
import threading
import time
from collections import OrderedDict
from pathlib import Path

from .sources import SourceError, fetch_seed_work, pdf_availability, slim

PDF_MAX_BYTES = 60 * 1024 * 1024
IMPORT_TTL_SECONDS = 24 * 3600
SEED_CACHE_LIMIT = 200

_ARXIV = re.compile(r"(?:arxiv:)?(\d{4}\.\d{4,5})(v\d+)?", re.I)
_ARXIV_URL = re.compile(r"https?://(?:www\.)?arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})(v\d+)?(?:\.pdf)?/?", re.I)
_DOI = re.compile(r"10\.\d{4,9}/\S+")
_DOI_URL = re.compile(r"https?://(?:dx\.)?doi\.org/(10\.\d{4,9}/\S+)", re.I)
_OPENALEX = re.compile(r"(?:https?://openalex\.org/)?(W\d+)", re.I)
_PDF_ID = re.compile(r"[0-9a-f]{64}")

# Resolved papers are remembered between the lookup and the project creation request, so a seed the
# user already saw resolve is not fetched (and rate-limited) a second time. The App object is rebuilt
# for every request, hence module state.
_SEED_CACHE = OrderedDict()
_SEED_LOCK = threading.Lock()


def parse_seed(text):
    """(identifier for OpenAlex, arXiv id or None, dedupe key) or ValueError for free text."""
    seed = str(text or "").strip()
    seed = re.sub(r"^doi:\s*", "", seed, flags=re.I).rstrip(".,;")
    match = _ARXIV.fullmatch(seed) or _ARXIV_URL.fullmatch(seed)
    if match:
        arxiv_id = match.group(1)
        return f"https://doi.org/10.48550/arxiv.{arxiv_id}{match.group(2) or ''}", arxiv_id, arxiv_id
    doi_url = _DOI_URL.fullmatch(seed)
    if doi_url:
        seed = doi_url.group(1)
    if _DOI.fullmatch(seed):
        return f"https://doi.org/{seed}", None, f"https://doi.org/{seed}".lower()
    work = _OPENALEX.fullmatch(seed)
    if work:
        wid = work.group(1).upper()
        return wid, None, wid
    # Only public identifiers leave the machine; free text is looked up by search, not as an identifier.
    raise ValueError("无法识别的标识：请填 arXiv 编号、DOI 或 OpenAlex W 编号，或改用名称检索")


def _remember(paper):
    wid = _OPENALEX.search(paper.get("openalex_id") or "")
    if not wid:
        return
    with _SEED_LOCK:
        _SEED_CACHE[wid.group(1).upper()] = paper
        _SEED_CACHE.move_to_end(wid.group(1).upper())
        while len(_SEED_CACHE) > SEED_CACHE_LIMIT:
            _SEED_CACHE.popitem(last=False)


def _cached(identifier):
    wid = _OPENALEX.fullmatch(identifier)
    if not wid:
        return None
    with _SEED_LOCK:
        paper = _SEED_CACHE.get(wid.group(1).upper())
    return dict(paper) if paper else None


def fetch_seed_paper(client, identifier, arxiv_id=None):
    """One slim public-metadata paper for a parsed identifier; SourceError on lookup failure."""
    paper = _cached(identifier)
    if paper:
        return paper
    paper = slim(fetch_seed_work(client, identifier, arxiv_id) or {}, group="seed")
    paper["arxiv_id"] = paper["arxiv_id"] or arxiv_id
    if paper.get("key") and paper.get("title"):
        _remember(paper)
    return paper


def paper_view(paper, abstract_limit=1200):
    """What the creation page may show about a paper; never the stored/private state."""
    arxiv_id, doi = paper.get("arxiv_id"), paper.get("doi") or ""
    url = (f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id
           else doi if doi.startswith("http") else paper.get("openalex_id"))
    return {"key": paper.get("key"), "title": paper.get("title"),
            "abstract": (paper.get("abstract") or "")[:abstract_limit],
            "published": paper.get("published"), "source": paper.get("source"),
            "authors": paper.get("authors") or [], "openalex_id": paper.get("openalex_id"),
            "doi": doi or None, "arxiv_id": arxiv_id, "url": url, "match_mode": paper.get("match_mode"),
            "pdf_status": pdf_availability(arxiv_id, paper.get("oa") if "oa" in paper else paper.get("oa_json"))}


def source_failure(exc):
    kind = getattr(exc, "kind", None) or "failed"
    return {"status": kind, "error": str(exc)[:200]}


def lookup_seed(client, text):
    """Resolve one typed/pasted identifier. Expected failures come back as a status, not an exception."""
    text = str(text or "").strip()
    if not text or len(text) > 300:
        raise ValueError("请输入 DOI、arXiv 编号或链接（不超过 300 个字符）")
    try:
        identifier, arxiv_id, _ = parse_seed(text)
    except ValueError as exc:
        return {"status": "invalid_input", "error": str(exc)}
    try:
        paper = fetch_seed_paper(client, identifier, arxiv_id)
    except SourceError as exc:
        return source_failure(exc)
    except Exception as exc:
        return {"status": "failed", "error": str(exc)[:200]}
    if not paper.get("key") or not paper.get("title"):
        return {"status": "not_found", "error": "公开元数据缺少论文标题"}
    return {"status": "resolved", "paper": paper_view(paper)}


def search_seeds(client, query):
    """Paper-name search for the seed picker. The user typed the query; it is the only thing sent."""
    query = re.sub(r"\s+", " ", str(query or "")).strip()
    if len(query) < 3 or len(query) > 200:
        raise ValueError("请输入至少 3 个字符的论文名称（不超过 200 个字符）")
    try:
        papers = client.search_works(query)
    except SourceError as exc:
        return {**source_failure(exc), "items": []}
    except Exception as exc:
        return {"status": "failed", "error": str(exc)[:200], "items": []}
    for paper in papers:
        _remember(paper)
    return {"status": "ok" if papers else "empty", "items": [paper_view(p) for p in papers]}


# ------------------------------------------------------------------ imported PDFs
def import_pdf(data_dir, data, filename=""):
    """Keep a dropped PDF (original bytes, untouched) until a project creation attaches it."""
    if not isinstance(data, (bytes, bytearray)) or not bytes(data[:5]).startswith(b"%PDF"):
        raise ValueError("这不是 PDF 文件")
    if len(data) > PDF_MAX_BYTES:
        raise ValueError("PDF 超过 60 MB，无法导入")
    from .pdf_validation import validate_pdf
    validate_pdf(data)
    folder = Path(data_dir) / "imports"
    folder.mkdir(parents=True, exist_ok=True)
    cutoff = time.time() - IMPORT_TTL_SECONDS
    for old in folder.glob("*.pdf"):  # uploads nobody attached are not kept
        try:
            if old.stat().st_mtime < cutoff:
                old.unlink()
        except OSError:
            pass
    digest = hashlib.sha256(data).hexdigest()
    (folder / f"{digest}.pdf").write_bytes(bytes(data))
    name = re.sub(r"[^\w.\- ()一-鿿]", "_", Path(str(filename)).name)[:120] or "paper.pdf"
    return {"pdf_id": digest, "bytes": len(data), "filename": name}


def take_imported_pdf(data_dir, pdf_id):
    """Move an uploaded PDF into the library's pdfs folder and return its path."""
    if not isinstance(pdf_id, str) or not _PDF_ID.fullmatch(pdf_id):
        raise ValueError("PDF 标识无效")
    source = Path(data_dir) / "imports" / f"{pdf_id}.pdf"
    if not source.is_file():
        raise ValueError("导入的 PDF 已过期，请重新拖入")
    target_dir = Path(data_dir) / "pdfs"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"import-{pdf_id[:24]}.pdf"
    if target.exists():
        source.unlink()
    else:
        source.replace(target)
    return target


def archive_pdf(data_dir, sha256, source):
    """Copy a staged PDF into the library's pdfs folder, named by its content, and return the path.

    The copy is verified against `sha256` first, so a wrong or tampered staging file is never archived. An
    already archived file is left as it is (same content, same name), which makes a repeated commit safe.
    The staged source is not touched; the caller removes its staging folder once the import is committed."""
    if not isinstance(sha256, str) or not _PDF_ID.fullmatch(sha256):
        raise ValueError("PDF 标识无效")
    source = Path(source)
    digest = hashlib.sha256()
    with source.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != sha256:
        raise ValueError("PDF 内容和记录的不一致")
    target_dir = Path(data_dir) / "pdfs"
    target = target_dir / f"import-{sha256[:24]}.pdf"
    if target.exists():
        if hashlib.sha256(target.read_bytes()).hexdigest() != sha256:
            raise ValueError("已归档的 PDF 对不上，请先核对或重新获取文件")
        return target
    target_dir.mkdir(parents=True, exist_ok=True)
    import uuid
    partial = target_dir / (".import-" + uuid.uuid4().hex + ".part")
    try:
        shutil.copyfile(source, partial)
        if hashlib.sha256(partial.read_bytes()).hexdigest() != sha256:
            raise ValueError("复制期间 PDF 内容改变，请重新上传")
        partial.replace(target)
    finally:
        partial.unlink(missing_ok=True)
    return target


# ---------------------------------------------------------- why the AI did not answer
_REASONS = {
    "ai_off": ("AI 总开关已关闭", "The AI switch is off"),
    "no_key": ("还没有配置 DeepSeek 密钥，请到设置页填写", "No DeepSeek key is set; add one in Settings"),
    "not_approved": ("这项 AI 调用还没有获得批准", "This AI call has not been approved"),
    "budget": ("已达到每日或每月的额度上限", "A daily or monthly budget ceiling was reached"),
    "http": ("DeepSeek 拒绝了这次请求", "DeepSeek rejected the request"),
    "request_format": ("应用的 AI 请求缺少 JSON 输出声明，请更新应用后重试；草稿已保留 (HTTP 400)",
                       "The app's AI request is missing its JSON output instruction; update the app and retry. Your draft was preserved (HTTP 400)"),
    "network": ("请求没有成功（网络或超时）；这次的额度仍会计入", "The request did not complete (network or timeout); the budget for this call still counts"),
    "bad_reply": ("AI 回复为空或格式无效；请重新尝试，原有内容已保留", "The AI reply is empty or invalid; try again. Existing content was preserved"),
    "error": ("调用出现意外错误", "The call failed unexpectedly"),
    "dry_run": ("试运行：只预留额度，没有发送", "Dry run: budget reserved, nothing was sent"),
}


def degrade_reason(result, english=False):
    """(code, text) for why a gateway result did not produce an AI answer."""
    result = result or {}
    raw = str(result.get("reason") or "")
    status = result.get('http_status')
    if type(status) is not int:
        match = re.fullmatch(r'HTTPError: (\d{3})', raw)
        status = int(match.group(1)) if match else None
    if result.get("dry_run"):
        code = "dry_run"
    elif result.get("disabled"):
        code = "ai_off"
    elif result.get("invalid_input"):
        code = "invalid_input"
    elif raw == "no API key":
        code = "no_key"
    elif "awaiting owner approval" in raw:
        code = "not_approved"
    elif "ceiling" in raw or "budget exceeded" in raw:
        code = "budget"
    elif status == 400 and result.get('provider_error') == 'json_instruction_missing':
        code = "request_format"
    elif status is not None:
        code = "http"
    elif result.get('bad_reply'):
        code = 'bad_reply'
    elif result.get("usage_unknown") or raw.startswith(("URLError", "TimeoutError", "OSError")):
        code = "network"
    else:
        code = "error"
    text = reason_text(code, english)
    if code == 'http':
        details = {
            401: ('API 密钥无效，请在设置中检查或更换', 'The API key is invalid; check or replace it in Settings'),
            402: ('服务账户余额不足，请检查 DeepSeek 账户', 'The provider account has insufficient balance; check your DeepSeek account'),
            403: ('服务拒绝访问，请检查密钥权限', 'Access was denied; check the API key permissions'),
            429: ('请求频率过高或服务繁忙，请稍后重新尝试', 'The request rate is too high or the provider is busy; try again later'),
        }
        pair = details.get(status, ('AI 服务暂时不可用，请稍后重新尝试', 'The AI service is temporarily unavailable; try again later') if status >= 500
                           else ('服务拒绝请求，请检查设置或缩短输入后重新尝试', 'The provider rejected the request; check Settings or shorten the input and try again'))
        text = pair[int(bool(english))] + f' (HTTP {status})'
    elif code == 'invalid_input' and result.get('input_too_large'):
        text = ('This request is longer than the model can read at once; start a new session or shorten the selection. Nothing was sent.' if english
                else '这次内容超过了模型一次能读的最大长度；请开始新会话或缩短选区。未发送请求。')
    elif code == 'bad_reply' and result.get('finish_reason') == 'length':
        text = ('The AI reply was truncated at this request\'s output limit; the structured draft was incomplete. Try again; existing content was preserved.' if english
                else 'AI 回复被截断，达到本次输出长度上限；结构化草稿未完成，请重试，原有内容已保留。')
    elif code == 'budget':
        period = ('daily' if raw.startswith('daily') else 'monthly' if raw.startswith('monthly') else '')
        if period:
            resource = ('amount' if 'USD' in raw else 'token') if english else ('金额' if 'USD' in raw else 'token')
            text = (f'The {period} {resource} budget ceiling was reached; check usage in Settings or wait for the next budget period.' if english
                    else f'已达到{"每日" if period == "daily" else "每月"}{resource}额度上限；请在设置中查看用量，或等待额度周期更新。')
    if result.get('usage_unknown') or result.get('usage_reserved'):
        text += (' Billing is unknown; the budget for this call still counts.' if english else ' 费用未知，本次额度仍会计入。')
    return code, text


def reason_text(code, english=False):
    if code == 'invalid_input':
        return '请求文字格式无效，未发送请求。' if not english else 'Invalid request text; nothing was sent.'
    zh, en = _REASONS.get(code, _REASONS["error"])
    return en if english else zh

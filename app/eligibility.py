"""Local recommendation qualification; no network, models or interest inference."""
from collections import OrderedDict
import hashlib
import threading
from pathlib import Path

from .paper_language import title_metadata_evidence

MAX_PDF_BYTES = 128 * 1024 * 1024
BODY_PAGES = 6
BODY_PAGE_CHARS = 2000
MIN_BODY_CHARS = 200
MAX_VERIFY_BYTES = 256 * 1024 * 1024
_PDF_CACHE = OrderedDict()
_SCAN_CURSOR = OrderedDict()
_PDF_CACHE_LOCK = threading.RLock()
MAX_CACHED_DIGESTS = 1024
PLACEHOLDERS = {'n/a', 'na', 'none', 'null', 'no abstract', 'no abstract available',
                'abstract unavailable', '无摘要', '暂无摘要'}


def usable_abstract(value):
    text = str(value or '').strip()
    return bool(text and any(c.isalnum() for c in text)
                and text.lower().rstrip('.。') not in PLACEHOLDERS)


def retrieval_text(paper):
    content = paper.get("abstract") if usable_abstract(paper.get("abstract")) else paper.get("_local_body")
    return f"{paper.get('title') or ''} {content or ''}"


def usable_body(value):
    return sum(c.isalnum() for c in value) >= MIN_BODY_CHARS


def file_identity(path):
    try:
        path = Path(path)
        info = path.stat()
        return (str(path.resolve()), info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
    except (OSError, TypeError, ValueError):
        return None


def pdf_digest(path, budget=None):
    try:
        path = Path(path)
        info = path.stat()
        if not path.is_file() or info.st_size < 5 or info.st_size > MAX_PDF_BYTES:
            return None
        identity = (str(path.resolve()), info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
        with _PDF_CACHE_LOCK:
            if identity in _PDF_CACHE:
                _PDF_CACHE.move_to_end(identity)
                return _PDF_CACHE[identity]
        if budget is not None:
            if info.st_size > budget['remaining']:
                budget['deferred'] = True
                return None
            budget['remaining'] -= info.st_size
        digest = hashlib.sha256()
        with path.open('rb') as handle:
            prefix = handle.read(5)
            if prefix != b'%PDF-':
                return None
            digest.update(prefix)
            read = len(prefix)
            while read < info.st_size:
                # Never read beyond the size reserved for this pass. A growing file fails the final stat check.
                chunk = handle.read(min(1024 * 1024, info.st_size - read))
                if not chunk:
                    return None
                read += len(chunk)
                digest.update(chunk)
            result = digest.hexdigest()
            final = path.stat()
            if (final.st_dev, final.st_ino, final.st_size, final.st_mtime_ns, final.st_ctime_ns) != identity[1:]:
                return None
            with _PDF_CACHE_LOCK:
                _PDF_CACHE[identity] = result
                while len(_PDF_CACHE) > MAX_CACHED_DIGESTS:
                    _PDF_CACHE.popitem(last=False)
            return result
    except (OSError, TypeError, ValueError):
        return None


def verification_order(papers, scope):
    with _PDF_CACHE_LOCK:
        key = _SCAN_CURSOR.get(scope)
    start = next((i for i, paper in enumerate(papers) if paper['key'] == key), 0)
    return papers[start:] + papers[:start]


def defer_verification(scope, key):
    # Cache and cursor share a finite process lifetime; restarting safely starts a fresh pass.
    with _PDF_CACHE_LOCK:
        if key is None:
            _SCAN_CURSOR.pop(scope, None)
        else:
            _SCAN_CURSOR[scope] = key
            _SCAN_CURSOR.move_to_end(scope)
            while len(_SCAN_CURSOR) > MAX_CACHED_DIGESTS:
                _SCAN_CURSOR.popitem(last=False)


def has_pdf_source(paper):
    """Whether a legal PDF can be had for this paper: a PDF already stored here, an arXiv id, an https PDF link or an
    open-access landing page from the source. A paper without any of them is not recommended: there would be nothing to read."""
    if paper.get('current_pdf_path'):
        return True
    from .sources import pdf_availability
    return pdf_availability(paper.get('arxiv_id'), paper['oa'] if 'oa' in paper else paper.get('oa_json')) != 'none'


def evaluate(policy, paper, language, local_body=''):
    # Recompute from the current title, rather than trusting a cached/client
    # signal. _paper_language owns current-PDF proof; legacy direct callers
    # supplying only fulltext_language keep their existing verified priority.
    language = {**language, **title_metadata_evidence(paper.get('title'), language.get('metadata_language'))}
    fulltext_verified = bool(language.get('fulltext_language')) and language.get('fulltext_status', 'verified') == 'verified'
    reason = None
    if policy['status'] != 'ready':
        reason = 'language_policy_required'
    else:
        reported = (language.get('fulltext_language') if fulltext_verified else None) or language.get('metadata_language')
        if not reported:
            reason = 'language_unknown'
        elif (language.get('metadata_source') == 'chinese_text_over_metadata' and not fulltext_verified
              and policy['allowed_languages'] == ['en']):
            # The source said English but the text is clearly Chinese: an English-only project keeps it out, yet the person can
            # still rescue it by verifying the PDF (the same reason as the title-script gate).
            reason = 'title_language_unverified'
            language = {**language, 'title_metadata_conflict': True, 'title_warning': 'title_metadata_conflict'}
        elif reported not in policy['allowed_languages']:
            reason = 'language_not_allowed'
        elif policy['allowed_languages'] == ['en'] and language['title_metadata_conflict'] and not fulltext_verified:
            reason = 'title_language_unverified'
        elif not usable_abstract(paper.get('abstract')) and not usable_body(local_body):
            reason = 'no_readable_content'
        elif not has_pdf_source(paper):
            reason = 'no_pdf_source'
    return {'eligible': reason is None, 'reason': reason, 'language': language}


REASONS = {
    "fixed_scope_conflict": ("论文明确研究对象或治疗类型与固定目标冲突", "The stated object or treatment conflicts with the fixed goal"),
    "future_publication_date": ("来源报告了未来发布日期；请核对来源元数据后再推荐", "The source reports a future publication date; verify metadata before recommending"),
    "source_disabled": ("该论文所属来源已在设置中关闭", "This paper’s source is disabled in settings"),
    'language_policy_required': ('请先在项目设置选择允许的论文语言', 'Choose the allowed paper languages in project settings first'),
    'source_version_changed': ('PDF 版本已变化，请重新生成', 'The PDF version changed; generate again'),
    'source_verification_deferred': ('这次没来得及检查完所有文件，请再生成一次', 'Not every file could be checked this time; generate again'),
    'language_unknown': ('论文语言未知', 'Paper language is unknown'),
    'language_not_allowed': ('论文语言不符合项目设置', 'Paper language is not allowed by this project'),
    'title_language_unverified': ('标题文字与来源报告的英文语言存在冲突，请核验当前 PDF 的正文语言后再推荐',
                                  'The title script conflicts with the source English report; verify the current PDF body language before recommending'),
    'no_readable_content': ('没有可用摘要或当前版本的本地正文', 'No usable abstract or local text from the current PDF'),
    'no_pdf_source': ('没有可用的 PDF 来源', 'No PDF source is known'),
}

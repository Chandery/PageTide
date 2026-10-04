"""Guarded, user-triggered PDF download from open-access sources.

Zero model tokens. Only public URLs are requested, one paper at a time, and only because the user
opened or asked for that paper. Nothing here bypasses a paywall or uses credentials: a refusal
(403, robots.txt) is reported, not worked around.
"""
import hashlib
import json
import os
import re
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from pathlib import Path

from .creation import PDF_MAX_BYTES

UA = "PaperDigHelper/0.1 (local app; user-requested PDF download)"
ROBOTS_AGENT = "PaperDigHelper"
GAP_SECONDS = {"arxiv.org": 3.0}  # arXiv asks for at most one request every three seconds
DEFAULT_GAP_SECONDS = 1.0
MAX_WAIT_SECONDS = 10.0
MAX_CRAWL_DELAY_SECONDS = 60.0  # a robots.txt Crawl-delay is honoured up to this
MAX_REDIRECTS = 5
CHUNK = 64 * 1024
ARXIV_PDF = "https://arxiv.org/pdf/{}"


class PdfFetchError(RuntimeError):
    """kind: no_oa_source, invalid_url, robots_disallowed, not_found, paywalled_or_blocked,
    rate_limited, not_pdf, too_large or network_error."""

    def __init__(self, message, kind):
        super().__init__(message)
        self.kind = kind


class _HttpsOnly(urllib.request.HTTPRedirectHandler):
    max_redirections = MAX_REDIRECTS

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not newurl.lower().startswith("https://"):
            raise PdfFetchError(f"redirect to a non-https URL: {newurl}", "invalid_url")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _open(request, timeout=60):
    """The single network seam (tests replace it)."""
    return urllib.request.build_opener(_HttpsOnly).open(request, timeout=timeout)


def candidates(paper):
    """Ordered download candidates for a stored paper: its arXiv PDF, then OpenAlex's https links."""
    found = []
    if paper.get("arxiv_id"):
        found.append({"url": ARXIV_PDF.format(paper["arxiv_id"]), "kind": "arxiv", "license": None})
    try:
        oa = json.loads(paper.get("oa_json") or "null") or {}
    except ValueError:
        oa = {}
    seen = {c["url"] for c in found}
    for url in oa.get("pdf_urls") or []:
        if isinstance(url, str) and url.startswith("https://") and url not in seen:
            seen.add(url)
            found.append({"url": url, "kind": "openalex_oa", "license": oa.get("license")})
    return found


def stem_of(paper):
    """A filesystem-safe name stem from the canonical ID."""
    raw = paper.get("arxiv_id") or paper.get("key") or "paper"
    return re.sub(r"[^A-Za-z0-9._-]+", "_", raw).strip("._")[:60] or "paper"


class Fetcher:
    def __init__(self, dest_dir):
        self.dest = Path(dest_dir)
        self._last_request = {}
        self._robots = {}

    # ----------------------------------------------------------------- robots
    def _robots_allow(self, url):
        parts = urllib.parse.urlsplit(url)
        host = parts.netloc.lower()
        if host not in self._robots:
            robots_url = f"https://{host}/robots.txt"
            parser = urllib.robotparser.RobotFileParser()
            try:
                with _open(urllib.request.Request(robots_url, headers={"User-Agent": UA}), timeout=20) as response:
                    parser.parse(response.read(512 * 1024).decode("utf-8", "replace").splitlines())
            except urllib.error.HTTPError as exc:
                if 400 <= exc.code < 500:
                    parser.parse([])  # no robots.txt: nothing is disallowed
                else:
                    raise PdfFetchError(f"robots.txt unavailable for {host} (HTTP {exc.code})", "network_error") from exc
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                raise PdfFetchError(f"robots.txt unreachable for {host}: {exc}", "network_error") from exc
            self._robots[host] = parser
        return self._robots[host].can_fetch(ROBOTS_AGENT, url)

    # ---------------------------------------------------------------- pacing
    def _gap(self, host):
        """Seconds between requests to a host: our floor, or the site's robots Crawl-delay if longer."""
        gap = GAP_SECONDS.get(host, DEFAULT_GAP_SECONDS)
        parser = self._robots.get(host)
        delay = parser.crawl_delay(ROBOTS_AGENT) if parser else None
        try:
            delay = float(delay) if delay is not None else 0.0
        except (TypeError, ValueError):
            delay = 0.0
        return max(gap, min(delay, MAX_CRAWL_DELAY_SECONDS))

    def _pace(self, host):
        gap = self._gap(host)
        last = self._last_request.get(host)
        if last is not None:
            wait = gap - (time.monotonic() - last)
            if wait > 0:
                time.sleep(wait)
        self._last_request[host] = time.monotonic()

    # ------------------------------------------------------------------ fetch
    def fetch(self, url, stem):
        """Download one PDF; returns {path, sha256, bytes, url} or raises PdfFetchError."""
        parts = urllib.parse.urlsplit(url)
        if parts.scheme != "https" or not parts.netloc:
            raise PdfFetchError(f"only https PDF links are fetched: {url}", "invalid_url")
        host = parts.netloc.lower()
        if not self._robots_allow(url):
            raise PdfFetchError(f"robots.txt disallows {url}", "robots_disallowed")
        last_error = None
        for attempt in range(2):  # one retry, only for rate limiting and server errors
            self._pace(host)
            try:
                request = urllib.request.Request(url, headers={"User-Agent": UA})
                with _open(request, timeout=60) as response:
                    return self._save(response, url, stem)
            except urllib.error.HTTPError as exc:
                if exc.code in (401, 403):
                    raise PdfFetchError(f"HTTP {exc.code} from {host}", "paywalled_or_blocked") from exc
                if exc.code in (404, 410):
                    raise PdfFetchError(f"HTTP {exc.code}: no file at {url}", "not_found") from exc
                last_error = PdfFetchError(f"HTTP {exc.code} from {host}",
                                           "rate_limited" if exc.code == 429 else "network_error")
                if attempt == 0:
                    time.sleep(self._retry_delay(exc, host))
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_error = PdfFetchError(f"{host} unreachable: {exc}", "network_error")
                if attempt == 0:
                    time.sleep(min(DEFAULT_GAP_SECONDS * 2, MAX_WAIT_SECONDS))
        raise last_error

    def _retry_delay(self, exc, host):
        gap = self._gap(host)
        try:
            asked = float(exc.headers.get("Retry-After")) if exc.headers and exc.headers.get("Retry-After") else gap
        except (TypeError, ValueError):
            asked = gap
        return min(max(asked, gap), MAX_WAIT_SECONDS)

    def _save(self, response, url, stem):
        final_url = (response.geturl() if hasattr(response, "geturl") else None) or url
        if not str(final_url).lower().startswith("https://"):
            raise PdfFetchError(f"redirected to a non-https URL: {final_url}", "invalid_url")
        length = (response.headers.get("Content-Length") if response.headers else None)
        try:
            if length is not None and int(length) > PDF_MAX_BYTES:
                raise PdfFetchError(f"file is larger than {PDF_MAX_BYTES} bytes", "too_large")
        except ValueError:
            pass
        self.dest.mkdir(parents=True, exist_ok=True)
        digest, size = hashlib.sha256(), 0
        handle, temp = tempfile.mkstemp(dir=str(self.dest), prefix=".part-", suffix=".tmp")
        try:
            with os.fdopen(handle, "wb") as out:
                first = True
                while True:
                    chunk = response.read(CHUNK)
                    if not chunk:
                        break
                    if first:
                        if b"%PDF-" not in chunk[:1024]:
                            raise PdfFetchError("response is not a PDF (login or landing page?)", "not_pdf")
                        first = False
                    size += len(chunk)
                    if size > PDF_MAX_BYTES:
                        raise PdfFetchError(f"file is larger than {PDF_MAX_BYTES} bytes", "too_large")
                    digest.update(chunk)
                    out.write(chunk)
                if first:
                    raise PdfFetchError("empty response", "not_pdf")
            sha = digest.hexdigest()
            target = self.dest / f"{stem}-{sha[:12]}.pdf"
            if target.exists():
                os.unlink(temp)  # identical content already archived: keep the original
            else:
                os.replace(temp, target)
            return {"path": str(target), "sha256": sha, "bytes": size, "url": url}
        except BaseException:
            if os.path.exists(temp):
                os.unlink(temp)
            raise

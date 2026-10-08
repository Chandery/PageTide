"""Guarded, user-triggered PDF download from open-access sources.

Zero model tokens. Only public URLs are requested, one paper at a time, and only because the user
opened or asked for that paper. Nothing here bypasses a paywall or uses credentials: a refusal
(403, robots.txt) is reported, not worked around.
"""
import hashlib
import http.client
import ipaddress
import json
import os
import re
import tempfile
import threading
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
ROBOTS_TTL_SECONDS = 24 * 3600  # a long-running desktop session must not trust a robots answer forever
CHUNK = 64 * 1024
ARXIV_PDF = "https://arxiv.org/pdf/{}"


class PdfFetchError(RuntimeError):
    """kind: no_oa_source, invalid_url, robots_disallowed, not_found, paywalled_or_blocked,
    rate_limited, not_pdf, too_large or network_error."""

    def __init__(self, message, kind):
        super().__init__(message)
        self.kind = kind


_DNS_NAME = re.compile(r"[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+")
_LOCAL_SUFFIXES = (".localhost", ".local", ".internal", ".lan", ".home.arpa", ".localdomain")


def _host_of(parts):
    """Lower-case host without userinfo and without a trailing dot (arxiv.org. is arxiv.org)."""
    host = (parts.hostname or "").rstrip(".")
    return host


def _authority(parts):
    """host[:port] without userinfo, the key for robots.txt, pacing and locks (IPv6 in brackets)."""
    host = _host_of(parts)
    port = parts.port  # ValueError for a malformed port; callers map it to invalid_url
    shown = f"[{host}]" if ":" in host else host
    return shown if port in (None, 443) else f"{shown}:{port}"


def _require_public_https(url):
    """Only https URLs on public hosts. A host must be a public IP literal or a dotted DNS name:
    private/loopback addresses, alternate IPv4 spellings (2130706433, 0x7f.1, 127.1), single-label
    names and local suffixes are refused."""
    try:
        parts = urllib.parse.urlsplit(url)
        host = _host_of(parts)
        _authority(parts)
    except ValueError as exc:
        raise PdfFetchError(f"malformed URL: {url}", "invalid_url") from exc
    if parts.scheme != "https" or not host:
        raise PdfFetchError(f"only https PDF links are fetched: {url}", "invalid_url")
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        if not literal.is_global:
            raise PdfFetchError(f"refusing a non-public address: {host}", "invalid_url")
        return parts
    if (not _DNS_NAME.fullmatch(host) or host.rsplit(".", 1)[-1].isdigit() or host.endswith(_LOCAL_SUFFIXES)):
        raise PdfFetchError(f"refusing a host that is not a public DNS name: {host}", "invalid_url")
    return parts


class _Redirects(urllib.request.HTTPRedirectHandler):
    """Every hop must be https on a public host; `gate` also applies robots.txt and pacing to it."""
    max_redirections = MAX_REDIRECTS

    def __init__(self, gate=None):
        self.gate = gate

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _require_public_https(newurl)
        if self.gate:
            self.gate(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _open(request, timeout=60, gate=None):
    """The single network seam (tests replace it)."""
    return urllib.request.build_opener(_Redirects(gate)).open(request, timeout=timeout)


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
    """One per data directory and shared by every request (see shared_fetcher): robots.txt answers and
    the time of the last request to each host must outlive a single HTTP request to be of any use."""

    def __init__(self, dest_dir):
        self.dest = Path(dest_dir)
        self._last_request = {}
        self._robots = {}
        self._locks = {}
        self._guard = threading.Lock()

    def _host_lock(self, authority):
        with self._guard:
            return self._locks.setdefault(authority, threading.RLock())

    # ----------------------------------------------------------------- robots
    def _robots_allow(self, url):
        parts = urllib.parse.urlsplit(url)
        authority = _authority(parts)
        with self._host_lock(authority):
            cached = self._robots.get(authority)
            if cached is None or time.monotonic() - cached[1] > ROBOTS_TTL_SECONDS:
                robots_url = f"https://{authority}/robots.txt"
                parser = urllib.robotparser.RobotFileParser()
                try:
                    with _open(urllib.request.Request(robots_url, headers={"User-Agent": UA}), timeout=20) as response:
                        parser.parse(response.read(512 * 1024).decode("utf-8", "replace").splitlines())
                except urllib.error.HTTPError as exc:
                    if exc.code == 429 or exc.code >= 500 or 300 <= exc.code < 400:
                        raise PdfFetchError(f"robots.txt unavailable for {authority} (HTTP {exc.code})", "network_error") from exc
                    parser.parse([])  # other 4xx: no robots.txt, so nothing is disallowed
                except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException, ValueError) as exc:
                    raise PdfFetchError(f"robots.txt unreachable for {authority}: {exc}", "network_error") from exc
                cached = self._robots[authority] = (parser, time.monotonic())
            return cached[0].can_fetch(ROBOTS_AGENT, url)

    # ---------------------------------------------------------------- pacing
    def _gap(self, authority):
        """Seconds between requests to a host: our floor, or the site's robots Crawl-delay if longer."""
        host = authority.split(":")[0]
        gap = GAP_SECONDS.get(host, DEFAULT_GAP_SECONDS)
        cached = self._robots.get(authority)
        delay = cached[0].crawl_delay(ROBOTS_AGENT) if cached else None
        try:
            delay = float(delay) if delay is not None else 0.0
        except (TypeError, ValueError):
            delay = 0.0
        return max(gap, min(delay, MAX_CRAWL_DELAY_SECONDS))

    def _pace(self, authority):
        """Wait out the gap since the last request to this host. The robots.txt fetch itself is not
        counted (usual crawler practice), so a first download is not delayed by it."""
        with self._host_lock(authority):
            last = self._last_request.get(authority)
            if last is not None:
                wait = self._gap(authority) - (time.monotonic() - last)
                if wait > 0:
                    time.sleep(wait)
            self._last_request[authority] = time.monotonic()

    def _redirect_gate(self, url):
        """robots.txt and pacing for a redirect target, which may be a different host."""
        if not self._robots_allow(url):
            raise PdfFetchError(f"robots.txt disallows {url}", "robots_disallowed")
        self._pace(_authority(urllib.parse.urlsplit(url)))

    # ------------------------------------------------------------------ fetch
    def fetch(self, url, stem):
        """Download one PDF; returns {path, sha256, bytes, url} or raises PdfFetchError."""
        parts = _require_public_https(url)
        authority = _authority(parts)
        if not self._robots_allow(url):
            raise PdfFetchError(f"robots.txt disallows {url}", "robots_disallowed")
        last_error = None
        for attempt in range(2):  # one retry, only for rate limiting and server errors
            self._pace(authority)
            try:
                request = urllib.request.Request(url, headers={"User-Agent": UA})
                with _open(request, timeout=60, gate=self._redirect_gate) as response:
                    return self._save(response, url, stem)
            except urllib.error.HTTPError as exc:
                if exc.code in (401, 403):
                    raise PdfFetchError(f"HTTP {exc.code} from {authority}", "paywalled_or_blocked") from exc
                if exc.code in (404, 410):
                    raise PdfFetchError(f"HTTP {exc.code}: no file at {url}", "not_found") from exc
                last_error = PdfFetchError(f"HTTP {exc.code} from {authority}",
                                           "rate_limited" if exc.code == 429 else "network_error")
                if attempt == 0:
                    time.sleep(self._retry_delay(exc, authority))
            except (http.client.InvalidURL, ValueError) as exc:  # includes UnicodeError; retrying cannot help
                raise PdfFetchError(f"malformed URL: {url}", "invalid_url") from exc
            except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException) as exc:
                last_error = PdfFetchError(f"{authority} unreachable: {exc}", "network_error")
                if attempt == 0:
                    time.sleep(min(DEFAULT_GAP_SECONDS * 2, MAX_WAIT_SECONDS))
        raise last_error

    def _retry_delay(self, exc, authority):
        gap = self._gap(authority)
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
            from .pdf_validation import validate_pdf
            try:
                validate_pdf(temp)
            except ValueError as exc:
                raise PdfFetchError(str(exc), "not_pdf") from exc
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


_SHARED = {}
_SHARED_LOCK = threading.Lock()


def shared_fetcher(dest_dir):
    """The process-wide Fetcher for a data directory (the HTTP server builds a new App per request)."""
    key = str(Path(dest_dir).resolve())
    with _SHARED_LOCK:
        return _SHARED.setdefault(key, Fetcher(dest_dir))

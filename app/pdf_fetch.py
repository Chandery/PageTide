"""Guarded, user-triggered PDF download from open-access sources.

Zero model tokens. Only public URLs are requested, one paper at a time, and only because the user
opened or asked for that paper. Nothing here bypasses a paywall or uses credentials: a refusal (403) is reported, not
worked around. robots.txt rules automated crawling; a download the person asked for, one paper at a time, is the
person's own action, as in a browser, and does not consult it (owner, 2026-10-26: IOP's robots.txt refuses every
program, while the same PDF downloads from its page). An automated caller passes user_requested=False.
"""
import hashlib
import http.client
import ipaddress
import json
import os
import re
import socket
import ssl
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from pathlib import Path

from .creation import PDF_MAX_BYTES

UA = "PageTide/0.1 (local app; user-requested PDF download)"
ROBOTS_AGENT = "PageTide"
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
    rate_limited, not_pdf, too_large, certificate_error or network_error."""

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
        newurl = iri_to_uri(newurl)
        _require_public_https(newurl)
        if self.gate:
            self.gate(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def iri_to_uri(url):
    """A link as a browser sends it: non-ASCII in the path or query percent-encoded (UTF-8), an international host in
    its ASCII form. A publisher link such as .../download/129680071/lowqualitypdf/<Chinese title>.pdf was refused as
    malformed while the browser opened it (2026-10-26). Characters already escaped stay as they are."""
    try:
        parts = urllib.parse.urlsplit(url)
        host = parts.hostname or ""
        if host and not host.isascii():
            ascii_host = host.encode("idna").decode("ascii")
            netloc = parts.netloc.replace(parts.hostname, ascii_host)
        else:
            netloc = parts.netloc
    except (ValueError, UnicodeError):
        return url
    keep = "/%:@!$&'()*+,;=-._~?"
    return urllib.parse.urlunsplit((parts.scheme, netloc, urllib.parse.quote(parts.path, safe=keep),
                                    urllib.parse.quote(parts.query, safe=keep), urllib.parse.quote(parts.fragment, safe=keep)))


# ------------------------------------------------------------------ incomplete certificate chains
# Some sites send their own certificate without the intermediate that links it to a public root. Browsers fill the gap
# by downloading that intermediate from the address in the certificate ("CA Issuers"); Python does not, so the app said
# "network problem" where a browser downloaded the file (2026-10-26, www.jlakes.org). The same is done here, once per
# host. Safe because the fetched certificates are only extra links: the chain must still end at a public root in the
# trusted store, partial chains are not accepted, and a self-signed certificate fetched this way is never added.
_ISSUER_MISSING = (20, 21)        # X509_V_ERR_UNABLE_TO_GET_ISSUER_CERT_LOCALLY, _UNABLE_TO_VERIFY_LEAF_SIGNATURE
_CHAIN_CONTEXTS = {}
_CHAIN_LOCK = threading.Lock()
MAX_ISSUER_BYTES = 64 * 1024


def _issuer_missing(exc):
    reason = getattr(exc, "reason", exc)
    return isinstance(reason, ssl.SSLCertVerificationError) and getattr(reason, "verify_code", None) in _ISSUER_MISSING


def _decode_cert(pem):
    """The certificate's fields as ssl reports them (issuer, subject, caIssuers), or None."""
    handle, path = tempfile.mkstemp(suffix=".pem")
    try:
        with os.fdopen(handle, "w", encoding="ascii", errors="replace") as out:
            out.write(pem)
        return ssl._ssl._test_decode_cert(path)   # noqa: SLF001 - the stdlib's own decoder; no third-party parser
    except Exception:
        return None
    finally:
        os.unlink(path)


def _connect(host, port, timeout):
    """A socket to host:port the way the download goes: through the system's https proxy when there is one (a proxy can
    reach a different server of the same site, with a different certificate chain), else directly."""
    proxy = urllib.request.getproxies().get("https")
    if proxy and not urllib.request.proxy_bypass(host):
        parts = urllib.parse.urlsplit(proxy if "://" in proxy else "http://" + proxy)
        if parts.scheme == "http" and parts.hostname:
            raw = socket.create_connection((parts.hostname, parts.port or 80), timeout=timeout)
            try:
                raw.sendall(f"CONNECT {host}:{port} HTTP/1.1\r\nHost: {host}:{port}\r\n\r\n".encode("ascii"))
                answer = b""
                while b"\r\n\r\n" not in answer and len(answer) < 8192:
                    chunk = raw.recv(1024)
                    if not chunk:
                        break
                    answer += chunk
                if answer.split(b" ", 2)[1:2] != [b"200"]:
                    raise OSError("proxy refused the tunnel")
                return raw
            except BaseException:
                raw.close()
                raise
    return socket.create_connection((host, port), timeout=timeout)


def _server_pem(host, port, timeout=15):
    """The certificate a server presents, read without verifying it (only to find its issuer's address)."""
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    with _connect(host, port, timeout) as raw:
        with context.wrap_socket(raw, server_hostname=host) as tls:
            return ssl.DER_cert_to_PEM_cert(tls.getpeercert(binary_form=True))


def _issuer_pem(url, timeout=15):
    """A certificate from a "CA Issuers" address (http or https, public host), as PEM, or None."""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https"):
        return None
    try:
        _require_public_https(urllib.parse.urlunsplit(("https",) + tuple(parts[1:])))
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=timeout) as response:
            data = response.read(MAX_ISSUER_BYTES + 1)
    except (PdfFetchError, urllib.error.URLError, OSError, ValueError, http.client.HTTPException):
        return None
    if len(data) > MAX_ISSUER_BYTES:
        return None
    if data.lstrip().startswith(b"-----BEGIN CERTIFICATE-----"):
        return data.decode("ascii", "replace")
    try:
        return ssl.DER_cert_to_PEM_cert(data)
    except ValueError:
        return None


def chain_context(host, port, fetch_server=_server_pem, fetch_issuer=_issuer_pem):
    """A TLS context that also knows the intermediates this host leaves out, or None when they cannot be found."""
    key = (host, port)
    with _CHAIN_LOCK:
        if key in _CHAIN_CONTEXTS:
            return _CHAIN_CONTEXTS[key]
    try:
        pem = fetch_server(host, port)
    except (OSError, ssl.SSLError, ValueError):
        return None
    extra = []
    for _ in range(3):                                          # leaf -> intermediate -> (another intermediate)
        fields = _decode_cert(pem) or {}
        addresses = [u for u in fields.get("caIssuers") or () if isinstance(u, str)]
        issuer = next((found for found in map(fetch_issuer, addresses[:2]) if found), None)
        if not issuer:
            break
        decoded = _decode_cert(issuer) or {}
        if not decoded or decoded.get("issuer") == decoded.get("subject"):
            break                                               # a self-signed certificate is never trusted this way
        extra.append(issuer)
        pem = issuer
    if not extra:
        return None
    context = ssl.create_default_context()
    partial = getattr(ssl, "VERIFY_X509_PARTIAL_CHAIN", 0x80000)   # OpenSSL X509_V_FLAG_PARTIAL_CHAIN (Python < 3.10 has no name)
    context.verify_flags &= ~partial                            # an intermediate is a link, never an anchor
    context.load_verify_locations(cadata="".join(extra))
    with _CHAIN_LOCK:
        _CHAIN_CONTEXTS[key] = context
    return context


class _ChainHandler(urllib.request.HTTPSHandler):
    """https for every hop of a request, redirects included: a host that leaves out an intermediate certificate is tried
    once more with it (see chain_context). The host is the real one, also behind a proxy's tunnel."""

    def https_open(self, req):
        target = getattr(req, "_tunnel_host", None) or req.host
        parts = urllib.parse.urlsplit("//" + target)
        key = (parts.hostname, parts.port or 443)
        known = _CHAIN_CONTEXTS.get(key)
        try:
            return self.do_open(http.client.HTTPSConnection, req, context=known)
        except urllib.error.URLError as exc:
            if known is not None or not _issuer_missing(exc) or not parts.hostname:
                raise
            context = chain_context(*key)
            if context is None:
                raise
            return self.do_open(http.client.HTTPSConnection, req, context=context)


def _open(request, timeout=60, gate=None):
    """The single network seam (tests replace it)."""
    return urllib.request.build_opener(_Redirects(gate), _ChainHandler()).open(request, timeout=timeout)


def _certificate_problem(exc):
    reason = getattr(exc, "reason", exc)
    return isinstance(reason, ssl.SSLCertVerificationError)


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
                except PdfFetchError as exc:
                    if exc.kind != "invalid_url":
                        raise
                    parser.parse([])  # robots.txt moved off https (or off a public host): none is readable, as a 404
                except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException, ValueError) as exc:
                    kind = "certificate_error" if _certificate_problem(exc) else "network_error"
                    raise PdfFetchError(f"robots.txt unreachable for {authority}: {exc}", kind) from exc
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

    def _redirect_gate(self, url, user_requested=False):
        """Pacing (and, for an automated fetch, robots.txt) for a redirect target, which may be a different host."""
        if not user_requested and not self._robots_allow(url):
            raise PdfFetchError(f"robots.txt disallows {url}", "robots_disallowed")
        self._pace(_authority(urllib.parse.urlsplit(url)))

    # ------------------------------------------------------------------ fetch
    def fetch(self, url, stem, user_requested=False):
        """Download one PDF; returns {path, sha256, bytes, url} or raises PdfFetchError. user_requested: the person asked
        for this paper (see the module note), so robots.txt is not consulted; pacing and every other guard still apply."""
        url = iri_to_uri(url)
        parts = _require_public_https(url)
        authority = _authority(parts)
        if not user_requested and not self._robots_allow(url):
            raise PdfFetchError(f"robots.txt disallows {url}", "robots_disallowed")
        gate = (lambda target: self._redirect_gate(target, user_requested=True)) if user_requested else self._redirect_gate
        last_error = None
        for attempt in range(2):  # one retry, only for rate limiting and server errors
            self._pace(authority)
            try:
                request = urllib.request.Request(url, headers={"User-Agent": UA})
                with _open(request, timeout=60, gate=gate) as response:
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
                if _certificate_problem(exc):          # retrying cannot help, and it is not the person's network
                    raise PdfFetchError(f"{authority}: certificate not verifiable: {exc}", "certificate_error") from exc
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

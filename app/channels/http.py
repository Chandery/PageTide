"""Shared HTTP client for every channel (ADR 0010).

Extracted from the OpenAlex adapter: on-disk cache, bounded retries, Retry-After
bounded to 10 s, and one error type whose kind the UI can act on. Added here:
a minimum gap per host shared by all threads, cache lifetimes, and redaction so
an API key or contact address never reaches a cache name, an error or a log.

urllib.request.urlopen and time.sleep are looked up on their modules at call
time, so tests that patch app.sources.urllib.request.urlopen also patch this.
"""
import hashlib
import http.client
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

UA = "PaperDigHelper/0.1 (local research; read-only metadata)"
MAX_RETRY_WAIT = 10
SEARCH_TTL = 12 * 3600
LOOKUP_TTL = 30 * 86400
MAX_BODY = 20 * 1024 * 1024
# Query parameters whose values are credentials or personal contact details.
SECRET_PARAMS = {"api_key", "apikey", "api-key", "key", "token", "access_token", "wskey",
                 "mailto", "email", "insttoken"}
KINDS = {"not_found", "network_error", "unavailable", "invalid_input", "bad_response",
         "auth_required", "captcha", "quota_exhausted"}

_hosts_lock = threading.Lock()
_host_locks = {}
_host_last = {}


class SourceError(RuntimeError):
    """A metadata fetch failed. kind is one of KINDS; the message never contains a credential."""

    def __init__(self, message, kind):
        super().__init__(message)
        self.kind = kind


def _strip(url, replacement):
    parts = urllib.parse.urlsplit(url)
    if not parts.query:
        return url
    pairs = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    if replacement is None:
        kept = [(k, v) for k, v in pairs if k.lower() not in SECRET_PARAMS]
    else:
        kept = [(k, replacement if k.lower() in SECRET_PARAMS else v) for k, v in pairs]
    return urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(kept, safe="*")))


def redact(url):
    """The URL with every credential or contact value replaced by ***."""
    return _strip(url, "***")


def cache_name(url):
    """Cache file stem: credentials are dropped, so a new key reuses earlier results."""
    return hashlib.sha256(_strip(url, None).encode()).hexdigest()[:16]


def host_of(url):
    return urllib.parse.urlsplit(url).hostname or ""


def wait_for_host(host, gap):
    """Block until `gap` seconds have passed since the last request to this host (any thread)."""
    with _hosts_lock:
        lock = _host_locks.setdefault(host, threading.Lock())
    with lock:
        last = _host_last.get(host)
        if last is not None:
            remaining = last + gap - time.monotonic()
            if remaining > 0:
                time.sleep(remaining)
        _host_last[host] = time.monotonic()


class Client:
    def __init__(self, cache_dir, label="source", gap=2.0, user_agent=UA):
        self.cache = Path(cache_dir)
        self.cache.mkdir(parents=True, exist_ok=True)
        self.label = label
        self.gap = gap
        self.user_agent = user_agent

    def _cached(self, url, ttl):
        path = self.cache / f"{cache_name(url)}.json"
        if not path.exists():
            return path, None
        if ttl is not None and time.time() - path.stat().st_mtime > ttl:
            return path, None
        return path, path.read_text()

    def get(self, url, *, ttl=None, parse="json", headers=None, retries=2):
        """Fetch url and return the parsed body (dict for json, str for text).

        A body that does not parse is never cached. ttl=None keeps a cache entry forever.
        """
        path, body = self._cached(url, ttl)
        if body is not None:
            try:
                return self._parse(body, parse, url)
            except SourceError:
                path.unlink()  # a corrupt cache entry is refetched, not trusted
        host, shown = host_of(url), redact(url)
        last = None
        for attempt in range(retries):
            wait_for_host(host, self.gap)
            try:
                request = urllib.request.Request(url, headers={"User-Agent": self.user_agent, **(headers or {})})
                with urllib.request.urlopen(request, timeout=30) as response:
                    raw = response.read(MAX_BODY + 1)
                if len(raw) > MAX_BODY:
                    raise SourceError(f"{self.label} returned an oversized body ({host})", "bad_response")
                body = raw.decode("utf-8", "replace")
                payload = self._parse(body, parse, shown)
                path.write_text(body)
                return payload
            except http.client.InvalidURL as exc:
                raise SourceError(f"Invalid {self.label} request: {shown}", "invalid_input") from exc
            except urllib.error.HTTPError as exc:
                last = exc
                if exc.code == 404:
                    # A missing identifier will not appear on retry.
                    raise SourceError(f"{self.label} has no record: {shown}", "not_found") from exc
                if exc.code in (401, 403):
                    raise SourceError(f"{self.label} refused the request (HTTP {exc.code}); "
                                      "the API key may be missing or invalid", "auth_required") from exc
                if exc.code == 400:
                    raise SourceError(f"{self.label} rejected the query (HTTP 400): {shown}", "invalid_input") from exc
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                try:
                    delay = float(retry_after) if retry_after is not None else self.gap * (attempt + 1)
                except (TypeError, ValueError):
                    delay = self.gap * (attempt + 1)
                # Bound the wait: a hot shared API must not hang the app.
                time.sleep(min(max(delay, self.gap), MAX_RETRY_WAIT))
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last = exc
                time.sleep(min(self.gap * (attempt + 1), MAX_RETRY_WAIT))
        # 429/503 mean the service is shedding load, not a local network fault.
        busy = isinstance(last, urllib.error.HTTPError) and last.code in (429, 503)
        reason = f"HTTP {last.code}" if isinstance(last, urllib.error.HTTPError) else type(last).__name__
        raise SourceError(f"{self.label} fetch failed ({host}): {reason}", "unavailable" if busy else "network_error")

    def _parse(self, body, parse, shown):
        if parse == "text":
            return body
        try:
            return json.loads(body)
        except ValueError as exc:
            raise SourceError(f"{self.label} returned a non-JSON body: {shown}", "bad_response") from exc

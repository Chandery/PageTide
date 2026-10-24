#!/usr/bin/env python3
"""Local loopback HTTP API + static UI. Binds 127.0.0.1 only.

Threaded so a slow fetch or model call cannot freeze the whole page. Each
request uses its own short-lived App (and therefore its own SQLite connection),
which keeps storage thread-safe without sharing a connection across threads.
Long operations (refresh) run as background jobs the page can poll.
"""
import hmac
import json
import mimetypes
import os
import re
import sqlite3
import sys
import threading
import traceback
import subprocess
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from . import creation, demo, maintenance, onboarding, updater
from .organization import Conflict as OrganizationConflict
from .language import language
from .service import App, NoProject

STATIC = Path(__file__).resolve().parent / "static"
VERSION = "0.12"
JOBS = {}
JOBS_LOCK = threading.Lock()
JOB_SEQ = [0]
CATEGORY_REVIEW_CANCEL = {}
ORGANIZATION_JOB_LOCK = threading.Lock()
ORGANIZATION_PROCESSES_LOCK = threading.Lock()
ORGANIZATION_PROCESSES = set()
ORGANIZATION_STOPPING = threading.Event()
USER_SETTINGS_LOCK = threading.Lock()


def _static_version():
    """Max mtime of any file under STATIC, as an integer string.

    Used as a cache-buster query parameter on JS/CSS URLs injected into HTML
    responses so WKWebView treats every new build as a fresh resource.
    """
    try:
        mtimes = [f.stat().st_mtime for f in STATIC.rglob("*") if f.is_file()]
        return str(int(max(mtimes))) if mtimes else "0"
    except Exception:
        return "0"


def stop_organization_workers():
    ORGANIZATION_STOPPING.set()
    with ORGANIZATION_PROCESSES_LOCK:
        workers = list(ORGANIZATION_PROCESSES)
        for worker in workers:
            if worker.poll() is None:
                worker.terminate()
    for worker in workers:
        try:
            worker.wait(timeout=3)
        except subprocess.TimeoutExpired:
            worker.kill()
            worker.wait()


def organization_job(db_path, project, operation="suggest", body=None):
    """One bounded offline worker; no provider or user text on the command line.

    `body` (suggest only) is sent on stdin, e.g. the project's profile terms.
    """
    from . import organization_worker  # also included by the desktop packager
    if not ORGANIZATION_JOB_LOCK.acquire(blocking=False):
        raise ValueError("已有分类任务正在运行")
    try:
        command = ([sys.executable, "--organization-worker"] if getattr(sys, "frozen", False)
                   else [sys.executable, "-m", "app.organization_worker"])
        with ORGANIZATION_PROCESSES_LOCK:
            if ORGANIZATION_STOPPING.is_set():
                raise ValueError("应用正在退出")
            process = subprocess.Popen(command + [str(db_path), project, str(os.getpid()), operation]
                                       + (["stdin"] if body is not None else []),
                                       stdin=subprocess.PIPE if body is not None else subprocess.DEVNULL,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
                                       cwd=str(Path(__file__).resolve().parents[1]))
            ORGANIZATION_PROCESSES.add(process)
        try:
            stdout, stderr = process.communicate(
                input=None if body is None else json.dumps(body, ensure_ascii=True), timeout=120)
            if process.returncode:
                raise ValueError("本地分类失败：" + stderr[-500:])
            return json.loads(stdout)
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()
            with ORGANIZATION_PROCESSES_LOCK:
                ORGANIZATION_PROCESSES.discard(process)
    finally:
        ORGANIZATION_JOB_LOCK.release()


def suggestion_profile(app, project_id=None):
    """Local profile terms that steer category suggestions; nothing leaves the machine."""
    from .profile_insights import context, keywords
    from .service import PROFILE_STOPWORDS
    if project_id is not None and (not isinstance(project_id, str) or not app.projects.get_project(project_id)):
        raise ValueError("未知项目")
    project_id = project_id or app.require_default_project_id()
    project = app.projects.get_project(project_id) or {}
    return {"project": project.get("name") or project_id,
            "pinned": [term for term in app.profile(project_id)["pinned_terms"]
                       if isinstance(term, str) and 0 < len(term) <= 100][:40],
            "interest": [item["term"] for item in keywords(context(app, project_id), PROFILE_STOPWORDS)
                         if isinstance(item.get("term"), str) and 0 < len(item["term"]) <= 100][:40],
            "language": app.language()}


def category_review_job(root, project_id, all_papers=False, cancelled=None):
    """One explicit AI review job with its own short-lived connection."""
    from .category_review_service import run_review
    app = make_app(root)
    try:
        profile = suggestion_profile(app, project_id)
        scope = None if all_papers else (project_id or app.require_default_project_id())
        return run_review(app, scope, profile, cancelled=cancelled)
    finally:
        app.store.close()


# Credentials and usage accounting belong to the gateway, not cosmetic settings.
USER_SETTINGS_EXCLUDED = {"apiKey", "api_key", "dailyLimit", "aiRerank"}

# Every page loads these first: the language pack for the chosen interface language, then the
# layer that applies it (app/static/i18n.js). Chinese pages carry no pack at all.
I18N_SCRIPTS = b'<script src="/i18n/current.js"></script><script src="/i18n.js"></script>'


def i18n_script(lang):
    """window.PDH_I18N for the chosen language; the English pack is keyed by Chinese source text."""
    messages = {}
    if lang == "en-US":
        try:
            messages = json.loads((STATIC / "i18n" / "en-US.json").read_text(encoding="utf-8"))["messages"]
        except (OSError, ValueError, KeyError, TypeError):
            lang, messages = "zh-CN", {}   # a broken pack shows the Chinese source, never a blank page
    payload = json.dumps({"lang": lang, "messages": messages}, ensure_ascii=False)
    return ("window.PDH_I18N=" + payload.replace("</", "<\\/") + ";\n").encode()


def make_updater(root="."):
    """The update checker for this process. PDH_APP_VERSION is set only by the desktop shell: a source run has none,
    is a development build and never checks. Tests replace this to inject a fake transport."""
    return updater.Updater(data_dir(root), os.environ.get("PDH_APP_VERSION"))


def make_app(root="."):
    import os
    return App(root=root, data_dir=os.environ.get("PAPERDIGHELPER_DATA"))


def data_dir(root="."):
    """Resolved data directory, the same one App(root) uses, without opening the store.

    The desktop shell points PAPERDIGHELPER_DATA at Application Support; the CLI
    falls back to <root>/.local/app. Never hardcode a path here -- guessing
    ~/Documents wrote settings to a directory the app never reads.
    """
    return os.environ.get("PAPERDIGHELPER_DATA") or str(Path(root) / ".local" / "app")


def _job_start(name, fn):
    with JOBS_LOCK:
        JOB_SEQ[0] += 1
        job_id = f"job-{JOB_SEQ[0]}"
        JOBS[job_id] = {"id": job_id, "name": name, "state": "running", "result": None, "error": None}
    def runner():
        try:
            result = fn()
            with JOBS_LOCK:
                JOBS[job_id].update(state="done", result=result)
        except Exception as exc:  # keep the job failure visible, never silent
            with JOBS_LOCK:
                JOBS[job_id].update(state="failed", error=f"{type(exc).__name__}: {exc}",
                                    traceback=traceback.format_exc()[-800:])
    threading.Thread(target=runner, daemon=True).start()
    return dict(JOBS[job_id])


def _job_get(job_id):
    with JOBS_LOCK:
        return dict(JOBS.get(job_id) or {"error": "unknown job"})


# Library-import resolvers: one background thread per batch. Progress lives in the database (item states), so
# the registry only knows which threads are alive and how to ask one to stop.
IMPORT_WORKERS = {}
IMPORT_WORKERS_LOCK = threading.Lock()


def _import_worker_alive(batch_id):
    with IMPORT_WORKERS_LOCK:
        entry = IMPORT_WORKERS.get(batch_id)
        return bool(entry and entry[0].is_alive())


def _import_start(root, batch_id):
    """Start the resolver for a batch unless one is already running; True when a new thread was started."""
    with IMPORT_WORKERS_LOCK:
        entry = IMPORT_WORKERS.get(batch_id)
        if entry and entry[0].is_alive():
            return False
        cancel = threading.Event()

        def run():
            app = make_app(root)
            from .library_import import ResolveBusy
            try:
                app.library_import.resolve(batch_id, cancel=cancel)
            except ResolveBusy:
                pass   # another import holds OpenAlex; this batch was paused with that reason
            except Exception:  # the batch is left paused with its reason; the traceback is for the developer
                traceback.print_exc()
            finally:
                app.store.close()
        thread = threading.Thread(target=run, daemon=True)
        IMPORT_WORKERS[batch_id] = (thread, cancel)
        thread.start()
        return True


def _import_cancel(batch_id):
    with IMPORT_WORKERS_LOCK:
        entry = IMPORT_WORKERS.get(batch_id)
        if entry and entry[0].is_alive():
            entry[1].set()
            return True
        return False


class _CountedStream:
    """The request body, read at most `length` bytes; `remaining` says whether the caller left any unread."""

    def __init__(self, stream, length):
        self.stream, self.remaining = stream, length

    def read(self, size=-1):
        size = self.remaining if size is None or size < 0 else min(size, self.remaining)
        data = self.stream.read(size) if size else b""
        self.remaining -= len(data)
        return data


class Handler(BaseHTTPRequestHandler):
    server_version = "PaperDigHelper/0.6"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    def end_headers(self):
        self._response_started = True
        super().end_headers()

    def handle_one_request(self):
        """An exception nobody anticipated must not just drop the connection (the page and the packaged smoke
        test would only see "closed without response"). Log the traceback to stderr and answer 500 when no
        response has started. Request paths are not logged: they can carry the desktop token."""
        self._response_started = False
        self._demo = False
        try:
            super().handle_one_request()
        except Exception as exc:
            self.close_connection = True
            # A client that went away while we were writing a response is routine. The same error types raised
            # before any response started come from handler code (e.g. an upstream timeout): log those.
            if self._response_started and isinstance(exc, (ConnectionError, TimeoutError)):
                return
            if isinstance(exc, NoProject) and not self._response_started:
                # A route that needs a project was called before the person made one: a plain 400, not a crash.
                try:
                    self._json({"error": str(exc), "reason_code": "no_project"}, 400)
                except Exception:
                    pass
                return
            import traceback
            traceback.print_exc()
            if not self._response_started:
                try:
                    self._json({"error": "internal error"}, 500)
                except Exception:
                    pass

    _demo = False   # set per request by _demo_check: HTTP/1.1 reuses this object, so it is reset at the top of every do_*

    def _app(self):
        root = getattr(self.server, "root", ".")
        if self._demo:
            return demo.open_app(root, self._data())
        return make_app(root)

    def _demo_check(self, method, route, project_id=None, body=None):
        """Decide whether this request is the demo project's and whether the demo may do it. True: carry on (self._demo
        says which database). False: a 403 was sent. REAL_ONLY routes (settings, update, onboarding...) never become demo."""
        self._demo = False
        if demo.real_only(method, route) or not demo.requested(self.headers, project_id):
            return True
        if not demo.allowed(method, route, body):
            if body is None and method != "GET":
                self._drain_body()
            self._json(demo.blocked_payload(language(self._data()) == "en-US"), 403)
            return False
        self._demo = True
        return True

    def _drain_body(self):
        """A refused request's body must not be read as the next request on a kept-alive connection."""
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if 0 < length <= 2_000_000:
            self.rfile.read(length)
        elif length:
            self.close_connection = True

    def _data(self):
        # Settings, the language pack and App(root) must all read one directory.
        return data_dir(getattr(self.server, "root", "."))

    def _json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _route_beta_head(self):
        """Tell every page, before it renders, whether the beta learning-map mode is switched on in Settings.
        Elements marked data-route-beta are hidden while it is off; scripts read window.PDH_ROUTE_BETA."""
        from .user_settings import route_beta
        on = route_beta(self._data())
        return (b"<script>window.PDH_ROUTE_BETA=" + (b"true" if on else b"false") + b";"
                + (b"document.documentElement.classList.add('route-beta');" if on else b"") + b"</script>"
                b"<style>html:not(.route-beta) [data-route-beta],html.route-beta [data-route-beta-off]{display:none !important}</style>")

    def _static(self, path):
        target = (STATIC / ("index.html" if path in ("/", "") else path.lstrip("/"))).resolve()
        if not str(target).startswith(str(STATIC)) or not target.is_file():
            self.send_error(404)
            return
        body = target.read_bytes()
        if target.suffix == ".html":
            body = re.sub(rb"(<head(?:\s[^>]*)?>)", lambda m: m.group(1) + I18N_SCRIPTS + self._route_beta_head(), body, count=1)
            # Inject a cache-buster on every local JS/CSS URL so WKWebView
            # fetches the latest build instead of serving a stale cached copy.
            ver = _static_version().encode()
            body = re.sub(
                rb'((?:src|href)=")(\/[^"?]+\.(?:js|css))(")',
                lambda m: m.group(1) + m.group(2) + b"?v=" + ver + m.group(3),
                body,
            )
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(str(target))[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path, content_type="application/pdf", status=200):
        data = Path(path).read_bytes()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Disposition", "inline")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _desktop_access(self):
        token = getattr(self.server, "desktop_token", None)
        if token is None:
            allowed = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
            if self.headers.get("Host") not in allowed:
                self._json({"error": "invalid host"}, 403)
                return False
            return True
        authority = f"127.0.0.1:{self.server.server_port}"
        if self.headers.get("Host") != authority:
            self._json({"error": "invalid host"}, 403)
            return False
        if self.command == "GET" and hmac.compare_digest(self.path, f"/_desktop/{token}"):
            self.send_response(303)
            self.send_header("Location", "/")
            self.send_header("Set-Cookie", f"pdh_session={token}; HttpOnly; SameSite=Strict; Path=/")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return False
        cookie = SimpleCookie()
        cookie.load(self.headers.get("Cookie", ""))
        supplied = cookie["pdh_session"].value if "pdh_session" in cookie else ""
        if not hmac.compare_digest(supplied, token):
            self._json({"error": "desktop session required"}, 403)
            return False
        return True

    def _same_origin(self):
        """A browser page on another site always sends its own Origin; refuse it for every write."""
        origin = self.headers.get("Origin")
        return not origin or origin == "http://" + self.headers.get("Host", "")

    def _import_pdf(self):
        """A dropped PDF as raw bytes; kept untouched until a project creation attaches it to a seed."""
        origin = self.headers.get("Origin")
        if origin and origin != "http://" + self.headers.get("Host", ""):
            return self._json({"error": "cross-origin request denied"}, 403)
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self._json({"error": "invalid content length"}, 400)
        if length <= 0 or length > creation.PDF_MAX_BYTES:
            self.close_connection = True
            return self._json({"error": "PDF 大小必须在 60 MB 以内"}, 413)
        data = self.rfile.read(length)
        try:
            self._json(self._app().import_pdf(data, unquote(self.headers.get("X-Filename", ""))))
        except ValueError as exc:
            self._json({"error": str(exc)}, 400)

    # ----------------------------------------------------------- library import
    def _import_batch_pdf(self, route):
        """One PDF of an import batch as raw bytes (streamed to disk, never held whole in memory)."""
        from . import library_import
        parts = route.split("/")  # '', 'api', 'import', 'batches', <id>, 'pdf'
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0 or length > library_import.MAX_FILE_BYTES:
            self.close_connection = True
            return self._json({"error": "PDF 大小必须在 60 MB 以内"}, 413 if length > 0 else 400)
        body = _CountedStream(self.rfile, length)
        app = self._app()
        try:
            path = unquote(self.headers.get("X-Relative-Path", ""))
            try:
                modified = int(self.headers.get("X-Last-Modified") or 0)
            except ValueError:
                modified = 0
            hints = None
            raw_hints = unquote(self.headers.get("X-Import-Hints", ""))
            if raw_hints and len(raw_hints) <= 4096:
                try:
                    hints = json.loads(raw_hints)
                except ValueError:
                    hints = None
            self._json(app.library_import.add_pdf(parts[4], path, body, length, modified, hints))
        except ValueError as exc:
            self.close_connection = True
            self._json({"error": str(exc)}, 400)
        finally:
            if body.remaining:
                self.close_connection = True  # an unread body would be mistaken for the next request
            app.store.close()

    def _import_batch_sidecar(self, route):
        """The export file of a reference manager (a few MB of text at most), read whole and parsed in memory."""
        from . import reference_files
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0 or length > reference_files.MAX_BYTES:
            self.close_connection = True
            return self._json({"error": "导出文件大小必须在 20 MB 以内"}, 413 if length > 0 else 400)
        data = self.rfile.read(length)
        app = self._app()
        try:
            self._json(app.library_import.add_sidecar(route.split("/")[4], unquote(self.headers.get("X-Filename", "")), data))
        except ValueError as exc:
            self._json({"error": str(exc)}, 400)
        finally:
            app.store.close()

    def _import_get(self, route, query):
        app = self._app()
        try:
            imp = app.library_import
            if route == "/api/import/batches":
                project_id = query.get("project_id", [None])[0]
                if not project_id:
                    raise ValueError("缺少项目")
                return self._json({"batches": imp.list_batches(project_id)})
            batch_id = route[len("/api/import/batches/"):]

            if query.get("resume", [None])[0]:
                return self._json({"files": imp.resume_index(batch_id)})

            def number(name, default):
                try:
                    return int(query.get(name, [default])[0])
                except (TypeError, ValueError):
                    return default
            detail = imp.batch(batch_id, state=query.get("state", [None])[0], offset=number("offset", 0),
                               limit=number("limit", 200))
            detail["worker_alive"] = _import_worker_alive(batch_id)
            detail["openalex"] = app.openalex_status()
            if query.get("categories", [None])[0]:
                from .organization import Organization
                detail["categories"] = imp.category_preview(batch_id, Organization(app.store, project="default").directions())
            self._json(detail)
        except ValueError as exc:
            self._json({"error": str(exc)}, 400)
        finally:
            app.store.close()

    def _import_post(self, route, body):
        app = self._app()
        try:
            imp = app.library_import
            parts = route.split("/")  # '', 'api', 'import', 'batches', [<id>, <action>, [<item>]]
            if route == "/api/import/batches":
                project_id, source = body.get("project_id"), body.get("source")
                if not isinstance(project_id, str) or not isinstance(source, str):
                    raise ValueError("缺少项目或导入来源")
                return self._json(imp.create_batch(project_id, source, body.get("root_name"), body.get("options")))
            if len(parts) < 6 or parts[3] != "batches":
                return self._json({"error": "unknown route"}, 404)
            batch_id, action = parts[4], parts[5]
            if action == "resolve":
                imp.ensure_open(batch_id)
                _import_start(getattr(self.server, "root", "."), batch_id)
                return self._json({"started": True, "worker_alive": _import_worker_alive(batch_id)})
            if action == "cancel":
                return self._json({"cancelling": _import_cancel(batch_id)})
            if action == "commit":
                return self._json({"result": imp.commit(batch_id)})
            if action in ("discard", "settle") and _import_worker_alive(batch_id):
                raise ValueError("正在匹配，请先暂停再操作")   # a running resolver would write over the change
            if action == "discard":
                imp.discard(batch_id)
                return self._json({"discarded": True})
            if action == "settle":
                return self._json({"counts": imp.settle_rest(batch_id)})
            if action == "categories":
                from .organization import Organization
                return self._json({"result": imp.apply_categories(batch_id, Organization(app.store, project="default"))})
            if action == "seeds":
                keys, how = body.get("keys"), body.get("action")
                batch = imp.batch(batch_id, limit=0)
                if how == "add":
                    return self._json({"result": app.add_import_seeds(batch["project_id"], keys, batch_id=batch_id)})
                if how == "remove":
                    return self._json({"result": app.remove_import_seeds(batch["project_id"], keys)})
                raise ValueError("操作无效")
            if action == "items" and len(parts) == 7:
                try:
                    item_id = int(parts[6])
                except ValueError:
                    raise ValueError("导入条目不存在") from None
                return self._json({"item": imp.act(batch_id, item_id, body.get("action"), index=body.get("index"),
                                                   text=body.get("text"))})
            self._json({"error": "unknown route"}, 404)
        except ValueError as exc:
            self._json({"error": str(exc)}, 400)
        finally:
            app.store.close()

    def _body(self):
        length = int(self.headers.get("Content-Length") or 0)
        strict_route = urlparse(self.path).path == '/api/route' or (
            urlparse(self.path).path.startswith('/api/project-guidance/sessions/') and urlparse(self.path).path.endswith('/route'))
        limit = 1_000_000 if urlparse(self.path).path == '/api/route' else 131072
        if length < 0 or (strict_route and length > limit):
            raise ValueError('Route request body exceeds local limit')
        raw = self.rfile.read(length) or b"{}"
        if strict_route:
            from .route_revision import strict_json
            return strict_json(raw)
        return json.loads(raw)

    # -------------------------------------------------------------------- GET
    def do_GET(self):
        if not self._desktop_access():
            return
        parsed = urlparse(self.path)
        route, query = parsed.path, parse_qs(parsed.query)
        requested_project = query.get("project_id", [None])[0]
        if not self._demo_check("GET", route, requested_project):
            return
        if requested_project and route.startswith("/api/"):
            checker = self._app()
            if not checker.projects.get_project(requested_project):
                return self._json({"error": "项目不存在"}, 404)
        if route == "/i18n/current.js":
            body = i18n_script(language(self._data()))
            self.send_response(200)
            self.send_header("Content-Type", "text/javascript; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        if route == "/api/projects":
            return self._list_projects()
        if route == "/api/onboarding":
            return self._json(self._onboarding_state())
        if route == "/api/organization":
            return self._organization()
        if route == "/api/home":
            app = self._app()
            # Extract project_id from query if provided
            project_id = query.get("project_id", [None])[0]
            if not project_id and app.get_default_project_id() is None:
                return self._json(self._no_project_payload(app))
            self._json({**app.home_maintenance(project_id), "route": app.home_route(project_id),
                        "server_version": VERSION, "stats": app.stats(project_id),
                        "profile": app.profile(project_id),
                        "cards": app.cards(project_id=project_id), "summaries": app.store.summaries(),
                        "usage": app.usage(), "dev_mode": app.gateway.dev,
                        "provider": app.provider_status(),
                        "latest_jobs": [] if self._demo else list(JOBS.values())[-3:]})
        elif route == "/api/route":
            try:
                self._json(self._app().route_page(query.get("project_id", [None])[0]))
            except ValueError as exc:
                self._json({"error": str(exc)}, 400)
        elif route == "/api/settings":
            app = self._app()
            self._json(self._settings_payload(app))
        elif route == "/api/state":  # kept for compatibility
            app = self._app()
            project_id = query.get("project_id", [None])[0]
            if not project_id and app.get_default_project_id() is None:
                return self._json(self._no_project_payload(app))
            self._json({"profile": app.profile(project_id), "cards": app.cards(project_id=project_id)})
        elif route.startswith("/api/project-guidance/sessions/"):
            session_id = route.split("/")[-1]
            session = self._app().guidance_session_view(session_id)
            if not session:
                return self._json({"error": "引导会话不存在"}, 404)
            self._json({"session": session})
        elif route == "/api/paper":
            # Paper keys are URLs; prefer ?key= over a path segment.
            app = self._app()
            key = (query.get("key") or [""])[0]
            detail = app.paper_detail(key, query.get("project_id", [None])[0])
            if not detail:
                print(f"[404] paper key={key!r}", file=sys.stderr)
            self._json(detail or {"error": "not found", "key": key}, 200 if detail else 404)
        elif route.startswith("/api/paper/") and route.endswith("/projects"):
            app = self._app()
            key = unquote(route[len("/api/paper/"):-len("/projects")])
            self._json({"paper_key": key, "projects": app.store.paper_projects(key)})
        elif route.startswith("/api/paper/"):
            app = self._app()
            detail = app.paper_detail(unquote(route[len("/api/paper/"):]), query.get("project_id", [None])[0])
            self._json(detail or {"error": "not found"}, 200 if detail else 404)
        elif route == "/api/import/batches" or route.startswith("/api/import/batches/"):
            self._import_get(route, query)
        elif route.startswith("/api/jobs/"):
            self._json(_job_get(route[len("/api/jobs/"):]))
        elif route == "/api/library":
            app = self._app()
            project_id = query.get("project_id", [None])[0]
            self._json({"items": app.library(project_id), "stats": app.stats(project_id)})
        elif route == "/api/qa":
            app = self._app()
            self._json({"history": app.qa_history((query.get("key") or [""])[0], query.get("project_id", [None])[0])})
        elif route == "/api/fulltext":
            app = self._app()
            key = (query.get("key") or [""])[0]
            source_hash = (query.get('source_pdf_sha256') or [None])[0]
            status = app.fulltext_status(key, source_pdf_sha256=source_hash,
                                        include_texts=(query.get('text') or ['0'])[0]=='1')
            self._json(status)
        elif route == "/api/figure-page":
            app = self._app()
            self._json({"page": app.figure_page((query.get("key") or [""])[0], (query.get("q") or [""])[0])})
        elif route == "/api/pdf/view":
            app = self._app()
            key = (query.get("key") or [""])[0]
            digest = (query.get('sha256') or [None])[0]
            if digest:
                current = app.store.conn.execute('SELECT sha256 FROM pdfs WHERE paper_key=?', (key,)).fetchone()
                if not current or current['sha256'] != digest:
                    return self._json({'error': 'PDF 版本已变化，请重新打开论文'}, 409)
            path = app.pdf_path(key)
            if path:
                self._file(path, "application/pdf")
            else:
                self._json({"error": "pdf not downloaded yet"}, 404)
        elif route == "/api/profile":
            app = self._app()
            project_id = query.get("project_id", [None])[0]
            self._json({"profile": app.profile(project_id), "versions": app.profile_versions(project_id or app.get_default_project_id())})
        elif route == "/api/profile/insights":
            app = self._app()
            project_id = query.get("project_id", [None])[0]
            self._json(app.profile_insights(project_id))
        elif route == "/api/profile/evidence":
            try:
                offset = int(query.get("offset", [0])[0])
            except (TypeError, ValueError):
                self._json({"error": "无效的证据分页参数"}, 400)
                return
            if offset < 0:
                self._json({"error": "无效的证据分页参数"}, 400)
                return
            self._json(self._app().profile_evidence(
                query.get("project_id", [None])[0], query.get("kind", ["feedback"])[0],
                query.get("term", [""])[0], query.get("start", [None])[0],
                query.get("end", [None])[0], offset))
        elif route == "/api/weekly_report":
            from .weekly_report import generate_weekly_report
            app = self._app()
            project_id = query.get("project_id", [None])[0]
            if not project_id:
                return self._json({"error": "project_id required"}, 400)
            report = generate_weekly_report(project_id, app)
            self._json(report)
        elif route == "/api/export":
            app = self._app()
            from .local_snapshot import create_snapshot
            try:
                self._json(create_snapshot(app.store, app.data))
            except (OSError, ValueError, sqlite3.Error) as exc:
                self._json({'error': '结构化数据导出失败：' + str(exc)}, 500)
        elif route == "/api/data-location":
            root = Path(self._data()).resolve()
            self._json({'data_dir': str(root), 'pdf_dir': str(root / 'pdfs'), 'cache_dir': str(root / 'cache')})
        elif route == "/api/qa/session":
            from .reader_context import session, history
            app = self._app(); key = (query.get('key') or [''])[0]
            current = session(app.store, key, requested_project)
            self._json({'session': current, 'history': history(app.store, key, requested_project, current)})   # the same turns the model receives
        elif route == "/api/update":
            force = query.get("force", [""])[0] == "1"
            current = make_updater(getattr(self.server, "root", "."))
            result = current.check(force=force)
            result["apply_result"] = current.take_result()   # a macOS replacement that failed last time, reported once
            self._json(result)
        elif route == "/api/update/download":
            self._json(updater.download_state())
        elif route == "/api/user_settings":
            # GET settings from file
            settings_file = Path(self._data()) / "settings.json"
            if settings_file.exists():
                settings = json.loads(settings_file.read_text(encoding="utf-8"))
            else:
                settings = {}
            # Provider keys live only in the gateway key file, never here.
            settings = {k: v for k, v in settings.items() if k not in USER_SETTINGS_EXCLUDED}
            self._json({"settings": settings})
        else:
            self._static(route)

    # ------------------------------------------------------------------- POST
    def do_POST(self):
        self._demo = False
        if not self._desktop_access():
            return
        if not self._same_origin():
            return self._json({"error": "cross-origin request denied"}, 403)
        route = urlparse(self.path).path
        # Uploads are streamed straight to disk: the header alone decides, before any body is read. A page body that names
        # the demo project is checked once it is parsed (below).
        if (route == "/api/seeds/pdf" or route.startswith("/api/import/")) and not self._demo_check("POST", route):
            return
        if route in ("/api/organization", "/api/settings", "/api/route", "/api/ai-test", "/api/source-test"):
            # These routes mutate the local library, the learning map or store a credential: also cap the body.
            limit = {"/api/organization": 2_000_000, "/api/route": 1_000_000}.get(route, 8_000)
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                return self._json({"error": "invalid content length"}, 400)
            if length < 0 or length > limit:
                self.close_connection = True
                return self._json({"error": "request too large"}, 413)
        if route == "/api/seeds/pdf":
            return self._import_pdf()
        if route.startswith("/api/import/batches/") and route.endswith("/pdf") and route.count("/") == 5:
            return self._import_batch_pdf(route)
        if route.startswith("/api/import/batches/") and route.endswith("/sidecar") and route.count("/") == 5:
            return self._import_batch_sidecar(route)
        try:
            body = self._body()
        except (ValueError, json.JSONDecodeError, RecursionError):
            return self._json({"error": "invalid JSON"}, 400)
        if not isinstance(body, dict):
            return self._json({"error": "request must be an object"}, 400)
        if not self._demo_check("POST", route, body.get("project_id") if isinstance(body.get("project_id"), str) else None, body):
            return
        if route == "/api/onboarding":
            return self._onboarding_post(body)
        if route.startswith("/api/update/"):
            return self._update_post(route, body)
        if route == "/api/import/batches" or route.startswith("/api/import/batches/"):
            return self._import_post(route, body)
        if route == "/api/organization":
            if not isinstance(body, dict):
                return self._json({"error": "request must be an object"}, 400)
            return self._organization(body)
        if route == "/api/settings":
            if not isinstance(body, dict):
                return self._json({"error": "request must be an object"}, 400)
            app = self._app()
            if "source_key" in body or "clear_source_key" in body:
                # One key per source that uses one; the value is stored in that source's 0600 file and never echoed.
                try:
                    if "clear_source_key" in body:
                        app.clear_source_key(body["clear_source_key"])
                    else:
                        item = body["source_key"]
                        if not isinstance(item, dict) or set(item) != {"id", "value"} or not isinstance(item["value"], str):
                            raise ValueError("密钥请求无效")
                        app.save_source_key(item["id"], item["value"])
                except ValueError as exc:
                    return self._json({"error": str(exc)}, 400)
                return self._json(self._settings_payload(app))
            if "openalex_key" in body or body.get("clear_openalex_key"):
                try:
                    app.clear_openalex_key() if body.get("clear_openalex_key") else app.save_openalex_key(body["openalex_key"])
                except ValueError as exc:
                    return self._json({"error": str(exc)}, 400)
                return self._json(self._settings_payload(app))
            if "ai_enabled" in body:
                if not isinstance(body["ai_enabled"], bool):
                    return self._json({"error": "ai_enabled must be boolean"}, 400)
                app.gateway.set_enabled(body["ai_enabled"])
                return self._json(self._settings_payload(app))
            try:
                app.clear_api_key() if body.get("clear") else app.save_api_key(body.get("api_key") or "")
            except ValueError as exc:
                return self._json({"error": str(exc)}, 400)
            return self._json(self._settings_payload(app))
        app = self._app()
        if route == '/api/source-test':
            if (set(body) - {'id', 'api_key'} or not isinstance(body.get('id'), str)
                    or ('api_key' in body and not isinstance(body['api_key'], str))):
                return self._json({'error': '测试请求仅接受数据源 id 和可选的单行密钥'}, 400)
            try:
                return self._json(app.test_source(body['id'], body.get('api_key')))
            except ValueError as exc:
                return self._json({'error': str(exc)}, 400)
        if route == '/api/ai-test':
            if set(body) - {'api_key'} or ('api_key' in body and not isinstance(body['api_key'], str)):
                return self._json({'error': '测试请求仅接受可选的单行 API 密钥'}, 400)
            try:
                return self._json(app.test_ai_connection(body.get('api_key')))
            except OrganizationConflict:
                return self._json({'error': 'AI 连接测试正在进行，请等待本次结果'}, 409)
            except ValueError as exc:
                return self._json({'error': str(exc)}, 400)
        elif route == "/api/projects":
            # POST: create new project
            name = body.get("name")
            creation_mode = body.get("creation_mode", "manual")
            keywords = body.get("keywords", [])
            if not name:
                return self._json({"error": "name required"}, 400)
            try:
                result = app.create_project(name, creation_mode, keywords, body.get("seeds") or [],
                                            body.get("guidance_transcript"), body.get("learning_path"), route=body.get("route"),
                                            language_policy=body.get('language_policy'))
            except (ValueError, TypeError, sqlite3.IntegrityError) as exc:
                return self._json({"error": str(exc)}, 400)
            self._json(result)
        elif route.startswith("/api/projects/"):
            project_id = unquote(route[len("/api/projects/"):])
            try:
                if body.get('action') == 'language':
                    return self._json({'project': app.set_project_language(project_id, body.get('discipline'), body.get('allowed_languages'))})
                if body.get("action") != "rename":
                    return self._json({"error": "unknown project action"}, 400)
                self._json({"project": app.rename_project(project_id, body.get("name"))})
            except ValueError as exc:
                self._json({"error": str(exc)}, 404 if str(exc) == "项目不存在" else 400)
        elif route == "/api/project-papers":
            try:
                project_id, paper_key = body.get("project_id"), body.get("paper_key") or body.get("key")
                if not project_id or not paper_key:
                    raise ValueError("project_id and paper_key required")
                kind = body.get("relation_kind", "shared")
                if kind not in {"shared", "imported"}:
                    # "seed" is set only by project creation, which also updates the ranking seed set.
                    raise ValueError("relation_kind must be shared or imported")
                app.store.add_project_paper(project_id, paper_key, kind,
                                            body.get("source_project_id"))
                self._json({"project_id": project_id, "paper_key": paper_key, "added": True})
            except (ValueError, TypeError, sqlite3.IntegrityError) as exc:
                return self._json({"error": str(exc)}, 400)
        elif route in ("/api/seeds/resolve", "/api/seeds/search"):
            try:
                if route.endswith("resolve"):
                    self._json(app.seed_lookup(body.get("input")))
                else:
                    self._json(app.seed_search(body.get("query"), typed=body.get("typed") is not False))
            except (ValueError, TypeError) as exc:
                return self._json({"error": str(exc)}, 400)
        elif route == "/api/project-guidance/sessions":
            try:
                self._json({"session": app.create_guidance_session(body.get("name"), body.get("goal"), body.get("creation_mode", "ai_guided"))}, 201)
            except (ValueError, TypeError) as exc:
                return self._json({"error": str(exc)}, 400)
        elif route.startswith("/api/project-guidance/sessions/"):
            parts = route.split("/")
            if len(parts) < 5:
                return self._json({"error": "invalid guidance route"}, 404)
            session_id, action = parts[4], parts[5] if len(parts) > 5 else "turn"
            from .organization import Conflict
            try:
                if action == "turn":
                    self._json(app.guidance_turn(session_id, body.get("message"), bool(body.get("dry_run")),
                                                 retry=bool(body.get("retry")), draft_edits=body.get("draft"),
                                                 languages=body.get("languages"), base=body.get("base")))
                elif action == "search":
                    chosen = {"languages": body["languages"]} if "languages" in body else {}      # the paper languages ticked on the page
                    self._json(app.guidance_search(session_id, body.get("query"), all_years=bool(body.get("all_years")), **chosen))
                elif action == "preview":
                    chosen = {"languages": body["languages"]} if "languages" in body else {}
                    self._json(app.guidance_preview(session_id, body.get("draft"), **chosen))
                elif action == "route":
                    if 'brief' in body:
                        if set(body) - {'brief', 'regenerate', 'dry_run'}:
                            raise ValueError('固定需求创建请求包含未知字段')
                        if any(field in body and type(body[field]) is not bool for field in ('regenerate', 'dry_run')):
                            raise ValueError('创建选项必须是布尔值')
                        self._json(app.route_brief_plan(body['brief'], session_id=session_id,
                            regenerate=bool(body.get('regenerate')), dry_run=bool(body.get('dry_run'))))
                    else:
                        self._json(app.route_plan(session_id, regenerate=bool(body.get("regenerate")), dry_run=bool(body.get("dry_run")), boundary=body.get("boundary")))
                elif action == "finalize":
                    self._json(app.finalize_guidance(session_id, body.get("draft"), body.get("selected_keys"), route=body.get("route"),
                                                     language_policy=body.get('language_policy'), skip_route=body.get('skip_route', False)))
                else:
                    return self._json({"error": "unknown guidance action"}, 404)
            except Conflict as exc:
                return self._json({'error': str(exc)}, 409)
            except (ValueError, TypeError) as exc:
                return self._json({"error": str(exc)}, 400)
        elif route == "/api/refresh":
            include_distractors = bool(body.get("distractors"))
            pages = int(body.get("pages", 1))
            project_id = body.get("project_id")
            job = _job_start("refresh", lambda: maintenance.manual_refresh(
                make_app(getattr(self.server, "root", ".")), project_id, pages=pages, include_distractors=include_distractors))
            self._json(job)
        elif route == "/api/route":
            from .organization import Conflict
            action, project_id, revision = body.get("action"), body.get("project_id"), body.get("revision")
            try:
                revision_fields = {
                    'revision-preview': {'action', 'project_id', 'revision', 'brief', 'patch'},
                    'revision-confirm': {'action', 'project_id', 'draft_id'},
                    'revision-draft': {'action', 'project_id'},
                    'revision-generate': {'action', 'project_id', 'revision', 'brief', 'dry_run'},
                    'brief-plan': {'action', 'project_id', 'brief', 'dry_run'},
                }
                if action in revision_fields and set(body) - revision_fields[action]:
                    raise ValueError('修改预览请求包含未知字段')
                if action == "save":
                    result = app.route_save(project_id, plan=body.get("plan"), graph=body.get("graph"), revision=revision, brief=body.get("brief"))
                elif action == 'revision-preview':
                    return self._json(app.route_revision_preview(project_id, body.get('brief'), body.get('patch'), revision=revision))
                elif action == 'revision-confirm':
                    return self._json(app.route_revision_confirm(project_id, body.get('draft_id')))
                elif action == 'revision-draft':
                    return self._json({'draft': app.route_revision_draft(project_id)})
                elif action == 'revision-generate':
                    if 'dry_run' in body and type(body['dry_run']) is not bool:
                        raise ValueError('dry_run必须是布尔值')
                    return self._json(app.route_revision_generate(project_id, body.get('brief'), revision=revision,
                        dry_run=bool(body.get('dry_run'))))
                elif action == 'brief-plan':
                    if 'dry_run' in body and type(body['dry_run']) is not bool:
                        raise ValueError('dry_run必须是布尔值')
                    return self._json(app.route_brief_plan(body.get('brief'), project_id=project_id,
                        dry_run=bool(body.get('dry_run'))))
                elif action == "manual":
                    result = app.route_manual(project_id, body.get("concept"), body.get("value"), revision=revision)
                elif action == "watch":
                    result = app.route_watch(project_id, body.get("concept"), body.get("value"), revision=revision)
                elif action == "start":
                    result = app.route_start(project_id, body.get("start"), revision=revision)
                elif action == "mode":
                    result = app.route_mode(project_id, body.get("mode"), revision=revision)
                elif action == "candidates":
                    return self._json(app.route_candidates(project_id))
                elif action == "candidate-accept":
                    result = app.route_candidate_accept(project_id, body.get("candidate"), revision=revision)
                elif action == "undo":
                    result = app.route_undo(project_id, revision=revision, event=body.get("event"))
                elif action == "candidate-reject":
                    result = app.route_candidate_reject(project_id, body.get("candidate"), revision=revision)
                elif action == "ground":
                    return self._json({"graph": app.route_ground(body.get("graph"))})
                elif action == "concept-intro":
                    return self._json(app.route_concept_intro(project_id, body.get("concept"), dry_run=bool(body.get("dry_run"))))
                elif action == "direction-judge":
                    return self._json(app.route_direction_judge(project_id, dry_run=bool(body.get("dry_run"))))
                elif action == "concept-papers":
                    return self._json(app.route_concept_papers(project_id, body.get("concept")))
                elif action == "concept-examples":
                    return self._json(app.route_concept_examples(project_id, body.get("concept")))
                elif action == "plan":
                    return self._json(app.route_plan_project(project_id, body.get("goal"), boundary=body.get("boundary")))
                else:
                    return self._json({"error": "unknown route action"}, 400)
                self._json(result)
            except Conflict as exc:
                self._json({"error": str(exc)}, 409)
            except (ValueError, TypeError) as exc:
                self._json({"error": str(exc)}, 400)
            except sqlite3.Error:
                self._json({'error': '本地保存失败；原修改未保存，请保留草稿后重试'}, 500)
        elif route == "/api/maintain":
            if self._demo:   # nothing is fetched in the demo: no refresh is ever due
                return self._json({"due": False, "status": maintenance.status(app, demo.PROJECT_ID)})
            project_id = body.get("project_id") or app.get_default_project_id()
            if project_id is None:
                return self._json({"due": False, "status": None, "reason_code": "no_project"})
            wanted = maintenance.plan(app, project_id)
            if not (wanted["refresh"] or wanted["batch"]):
                self._json({"due": False, "status": maintenance.status(app, project_id)})
            else:
                root = getattr(self.server, "root", ".")
                self._json({"due": True, "plan": wanted,
                            "job": _job_start("maintain", lambda: maintenance.run(make_app(root), project_id))})
        elif route == "/api/daily":
            project_id = body.get("project_id")
            try:
                self._json(app.build_batch(limit=int(body["limit"]) if "limit" in body else None, project_id=project_id))
            except (ValueError, TypeError) as exc:
                return self._json({'error': str(exc)}, 400)
        elif route == "/api/triage":
            project_id = body.get("project_id")
            try:
                if self._demo:   # pre-written previews: no model, no token
                    return self._json(demo.triage(app, body.get("keys")))
                self._json(app.triage(app.cards(project_id=project_id), dry_run=bool(body.get("dry_run")), project_id=project_id,
                                      keys=body.get("keys")))
            except ValueError as exc:
                self._json({"error": str(exc)}, 400)
        elif route == "/api/feedback":
            key, action = body.get("key"), body.get("action")
            if not key or not action:
                return self._json({"error": "key and action required"}, 400)
            project_id = body.get("project_id")
            if "retract" in body and not isinstance(body["retract"], bool):
                return self._json({"error": "retract must be true or false"}, 400)
            try:
                if body.get("retract") is True:   # take back a familiarity mark pressed by mistake
                    self._json(app.retract_feedback(key, action, project_id))
                else:
                    self._json(app.record_feedback(key, action, body.get("reason"), project_id))
            except (ValueError, TypeError) as exc:
                return self._json({"error": str(exc)}, 400)
        elif route == "/api/undo":
            try:
                self._json(app.undo_feedback(int(body["feedback_id"]), body.get("project_id")))
            except (KeyError, ValueError, TypeError) as exc:
                return self._json({"error": str(exc)}, 400)
        elif route == "/api/unsave":
            try:
                self._json(app.unsave(body["key"], body.get("project_id")))
            except (KeyError, ValueError, TypeError) as exc:
                return self._json({"error": str(exc)}, 400)
        elif route == "/api/pin":
            project_id = body.get("project_id")
            self._json(app.pin_terms((body.get("terms") or "").replace("，", ",").split(","), project_id))
        elif route == "/api/profile/freeze":
            if not isinstance(body.get("frozen"), bool):
                return self._json({"error": "frozen must be a boolean"}, 400)
            try:
                self._json(app.set_profile_frozen(body["frozen"], body.get("project_id")))
            except ValueError as exc:
                return self._json({"error": str(exc)}, 400)
        elif route == "/api/profile/restore":
            try:
                self._json(app.restore_default_profile(body.get("project_id")))
            except ValueError as exc:
                return self._json({"error": str(exc)}, 400)
        elif route == "/api/library":
            app = self._app()
            project_id = body.get("project_id")
            self._json({"items": app.library(project_id), "stats": app.stats(project_id)})
        elif route == "/api/fulltext":
            try:
                self._json(app.save_fulltext(body.get("key") or "", body.get("pages") or [],
                                             source_pdf_sha256=body.get('source_pdf_sha256')))
            except (ValueError, TypeError) as exc:
                return self._json({"error": str(exc)}, 400)
        elif route == "/api/qa":
            try:
                self._json(app.qa(body.get("key"), body.get("question") or "", body.get("selection"),
                                  image=body.get("image"), page_hint=body.get("page_hint"),
                                  context=body.get("context") or "normal", project_id=body.get("project_id"),
                                  session_id=body.get('session_id'), reader_context=body.get('reader_context'),
                                  dry_run=bool(body.get("dry_run"))))
            except (ValueError, TypeError) as exc:
                return self._json({"error": str(exc)}, 400)
        elif route == "/api/qa/session":
            from .reader_context import new_session
            key, project = body.get('key'), body.get('project_id')
            if not isinstance(key, str) or not app.store.paper(key):
                return self._json({'error': '请选择论文后开始新会话'}, 400)
            if project and not app.store.conn.execute('SELECT 1 FROM project_papers WHERE project_id=? AND paper_key=?', (project, key)).fetchone():
                return self._json({'error': '论文不属于当前项目'}, 400)
            self._json({'session': new_session(app.store, key, project)})
        elif route == "/api/translate":
            self._json(app.translate(body.get("text") or "", dry_run=bool(body.get("dry_run"))))
        elif route == "/api/detail":
            # POST body avoids URL-encoding issues entirely; the UI uses this first.
            app = self._app()
            try:
                detail = app.paper_detail(body.get("key") or "", body.get("project_id"))
            except ValueError as exc:
                return self._json({"error": str(exc)}, 400)
            if not detail:
                print(f"[404] paper key={body.get('key')!r} (POST)", file=sys.stderr)
            self._json(detail or {"error": "not found", "key": body.get("key")}, 200 if detail else 404)
        elif route == "/api/pdf/prepare":
            self._json(app.download_pdf(body["key"]))
        elif route == "/api/pdf":
            self._json(app.download_pdf(body["key"]))
        elif route == "/api/pdf/attach":
            try:
                self._json(app.attach_pdf(body.get("key") or "", body.get("pdf_id")))
            except ValueError as exc:
                self._json({"error": str(exc)}, 400)
        elif route == "/api/weekly_report/analysis":
            # The local report is the source of truth.  Keep this endpoint
            # deterministic until the separately proposed weekly_digest
            # operation is approved for runtime use.
            from .weekly_report import generate_weekly_report
            project_id = body.get("project_id")
            if not project_id:
                return self._json({"error": "project_id required"}, 400)
            app = self._app()
            report = generate_weekly_report(project_id, app)
            stats = report["stats"]
            if app.english():
                if not report["has_activity"]:
                    analysis = ("No views, saves or feedback were recorded this week, "
                                "so no change of interest is inferred.")
                else:
                    n = stats["activity"]
                    parts = [f"{n} {'activity' if n == 1 else 'activities'} recorded this week"]
                    if stats["saved"]:
                        parts.append(f"{stats['saved']} positive feedback")
                    if stats["negative"]:
                        parts.append(f"{stats['negative']} explicitly marked not relevant")
                    if stats["too_hard"]:
                        parts.append(f"{stats['too_hard']} marked too hard")
                    analysis = ("; ".join(parts) + ". This summary only uses local records and never reads "
                                "a lack of action as a lack of interest.")
            elif not report["has_activity"]:
                analysis = "本周没有记录到浏览、收藏或反馈活动，因此不对兴趣变化作推断。"
            else:
                parts = [f"本周记录了 {stats['activity']} 次活动"]
                if stats["saved"]:
                    parts.append(f"有 {stats['saved']} 次正向反馈")
                if stats["negative"]:
                    parts.append(f"有 {stats['negative']} 次明确标记为不相关")
                if stats["too_hard"]:
                    parts.append(f"有 {stats['too_hard']} 次标记为太难")
                analysis = "，".join(parts) + "。这段总结只依据本地记录，不把没有动作解释成不感兴趣。"
            self._json({"analysis": analysis, "local": True, "report": report})
        elif route == "/api/user_settings":
            # POST: save settings
            settings_file = Path(self._data()) / "settings.json"
            settings_file.parent.mkdir(parents=True, exist_ok=True)
            settings = body.get("settings", {})
            if not isinstance(settings, dict):
                return self._json({"error": "settings must be an object"}, 400)
            settings = {k: v for k, v in settings.items() if k not in USER_SETTINGS_EXCLUDED}
            from .user_settings import read, validate
            try:
                settings = validate(settings)
                with USER_SETTINGS_LOCK:
                    if body.get('merge') is True:
                        settings = {**read(settings_file.parent), **settings}
                    import tempfile
                    with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=settings_file.parent, delete=False) as staged:
                        temporary = Path(staged.name)
                        json.dump(settings, staged, indent=2, ensure_ascii=False)
                        staged.flush(); os.fsync(staged.fileno())
                    try:
                        os.replace(temporary, settings_file)
                    finally:
                        temporary.unlink(missing_ok=True)
            except ValueError as exc:
                return self._json({'error': str(exc)}, 400)
            except OSError as exc:
                return self._json({'error': '设置未保存：' + str(exc)}, 500)
            self._json({"status": "saved"})
        elif route == "/api/cache":
            # DELETE cache (via POST with _method: DELETE)
            if body.get("_method") == "DELETE":
                cache_dir = Path(self._data()) / "cache"
                try:
                    if cache_dir.exists():
                        import shutil
                        shutil.rmtree(cache_dir)
                        cache_dir.mkdir(parents=True, exist_ok=True)
                except OSError as exc:
                    return self._json({'error': '清理没有完成：' + str(exc), 'preserved': ['pdf-archives', 'fulltext', 'notes', 'projects']}, 500)
                self._json({"status": "cleared", 'removed': ['source-response-cache'],
                            'preserved': ['pdf-archives', 'fulltext', 'notes', 'projects']})
            else:
                self._json({"error": "method not allowed"}, 405)
        else:
            self._json({"error": "unknown route"}, 404)

    def do_DELETE(self):
        self._demo = False
        if not self._desktop_access():
            return
        if not self._same_origin():
            return self._json({"error": "cross-origin request denied"}, 403)
        parsed = urlparse(self.path)
        route, query = parsed.path, parse_qs(parsed.query)
        if not self._demo_check("DELETE", route, query.get("project_id", [None])[0]):
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length) or b"{}") if length else {}
        except (ValueError, json.JSONDecodeError):
            return self._json({"error": "invalid JSON"}, 400)
        if route == "/api/project-papers":
            project_id = body.get("project_id") or (query.get("project_id") or [None])[0]
            paper_key = body.get("paper_key") or body.get("key") or (query.get("paper_key") or [None])[0]
            if not project_id or not paper_key:
                return self._json({"error": "project_id and paper_key required"}, 400)
            app = self._app()
            try:
                app.store.remove_project_paper(project_id, paper_key)
            except ValueError as exc:
                return self._json({"error": str(exc)}, 400)
            return self._json({"project_id": project_id, "paper_key": paper_key, "removed": True})
        if route.startswith("/api/projects/"):
            try:
                return self._json(self._app().delete_project(unquote(route[len("/api/projects/"):])))
            except ValueError as exc:
                return self._json({"error": str(exc)}, 404 if str(exc) == "项目不存在" else 400)
            except (OSError, sqlite3.Error) as exc:   # the backup came first, so nothing was deleted
                return self._json({"error": f"没能先备份数据库，所以没有删除：{exc}"}, 500)
        if route.startswith("/api/project-guidance/sessions/"):
            try:
                return self._json(self._app().cancel_guidance(route.split("/")[-1]))
            except LookupError as exc:
                return self._json({"error": str(exc)}, 404)
            except ValueError as exc:
                return self._json({"error": str(exc)}, 409)
        return self._json({"error": "unknown route"}, 404)

    def _update_post(self, route, body):
        """Download / apply / dismiss an update. Quitting afterwards is the page's job (PDHPrepareQuit keeps drafts safe)."""
        current = make_updater(getattr(self.server, "root", "."))
        try:
            if route == "/api/update/download":
                if not current.check()["available"]:
                    return self._json({"error": "没有可下载的新版本"}, 409)
                current.start_download()
                return self._json(updater.download_state())
            if route == "/api/update/apply":
                return self._json(current.apply())
            if route == "/api/update/cancel":
                current.cancel()
                return self._json({"ok": True})
            if route == "/api/update/dismiss":
                current.dismiss(body.get("version"))
                return self._json({"ok": True})
        except updater.UpdateError as exc:
            return self._json({"error": str(exc)}, 409)
        return self._json({"error": "unknown route"}, 404)

    @staticmethod
    def _settings_payload(app):
        """Provider, switch and accounting policy; never a saved or transient key."""
        limits = app.gateway.limits()
        return {"provider": app.provider_status(), "openalex": app.openalex_status(), "sources": app.sources_status(), "dev_mode": app.gateway.dev,
                "ai_enabled": app.gateway.enabled(), "usage": app.usage(),
                "aggregate_limits_enabled": bool(limits.get('aggregate_limits_enabled', True)),
                "limits": {k: limits[k] for k in ("daily_total_tokens", "monthly_total_tokens",
                                                   "daily_usd", "monthly_usd")}}

    @staticmethod
    def _no_project_payload(app):
        """/api/home and /api/state before the first project exists: 200 with nothing in it, so the page can send the
        person to project creation instead of showing an error."""
        return {"no_project": True, "maintenance": None, "recommendation_eligibility": None, "route": None,
                "server_version": VERSION, "stats": None, "profile": None, "cards": [], "summaries": {},
                "usage": app.usage(), "dev_mode": app.gateway.dev, "provider": app.provider_status(),
                "latest_jobs": []}

    def _list_projects(self):
        """GET /api/projects: the person's projects (the demo is never among them) plus a description of the demo, which the
        page adds to its project switcher only while the tour runs."""
        app = self._app()
        try:
            projects = app.projects.list_projects()
            english = app.english()
        finally:
            app.store.close()
        self._json({"projects": projects, "demo": demo.descriptor(english)})

    def _onboarding_state(self):
        app = make_app(getattr(self.server, "root", "."))
        try:
            count = len(app.projects.list_projects())
        finally:
            app.store.close()
        return onboarding.state(self._data(), getattr(self.server, "root", "."), count)

    def _onboarding_post(self, body):
        """{"action": "start"}: build a fresh demo sandbox. {"action": "done"}: this version's tour was seen (skip == finish)."""
        root = getattr(self.server, "root", ".")
        action = body.get("action")
        if action == "start":
            demo.reset(root, self._data())
            return self._json({"ok": True, "state": self._onboarding_state()})
        if action == "done":
            onboarding.mark_done(self._data(), root)
            return self._json({"ok": True, "state": self._onboarding_state()})
        self._json({"error": "unknown onboarding action"}, 400)

    def _organization(self, body=None):
        from .organization import Organization
        allowed_hosts = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
        if self.headers.get("Host") not in allowed_hosts:
            return self._json({"error": "invalid host"}, 403)
        app = self._app()
        try:
            # The current app is a single-project library. Keep its identity
            # stable when editable profile text changes.
            organization = Organization(app.store, project="default")
            if body is not None and not isinstance(body, dict):
                raise ValueError("请求必须是对象")
            if body and "op" in body and "action" in body and body["op"] != body["action"]:
                raise ValueError("conflicting operation fields")
            operation = body.get("op", body.get("action")) if body else None
            if operation == "route-detail":   # read-only and derived: nothing is stored, nothing needs a revision
                return self._json(app.route_detail(body.get("project_id"), body.get("focus_key")))
            if operation == "review-categories":
                # Validate the selected project before dispatch; the job reopens its own app.
                suggestion_profile(app, body.get('project_id'))
                cancelled = threading.Event()
                def run_category_review():
                    try:
                        return category_review_job(getattr(self.server, 'root', '.'), body.get('project_id'), body.get('scope') == 'all', cancelled.is_set)
                    finally:
                        with JOBS_LOCK:
                            for identifier, flag in list(CATEGORY_REVIEW_CANCEL.items()):
                                if flag is cancelled:
                                    CATEGORY_REVIEW_CANCEL.pop(identifier, None)
                job = _job_start('category-review', run_category_review)
                with JOBS_LOCK:
                    if JOBS[job['id']]['state'] == 'running':
                        CATEGORY_REVIEW_CANCEL[job['id']] = cancelled
                return self._json({'job': job})
            if operation == 'cancel-category-review':
                with JOBS_LOCK:
                    flag = CATEGORY_REVIEW_CANCEL.get(body.get('job_id'))
                    if flag is not None:
                        flag.set()
                return self._json({'cancel_requested': flag is not None})
            if operation in {"suggest", "graph"}:
                path = app.store.path.resolve()
                request = ({"profile": suggestion_profile(app, body.get("project_id")),
                            "scope_project": None if body.get("scope") == "all" else (body.get("project_id") or app.require_default_project_id())}
                           if operation == "suggest" else None)
                job = _job_start("organization", lambda: organization_job(path, "default", operation, request))
                return self._json({"job": job})
            self._json(organization.snapshot() if body is None else organization.action(body))
        except (ValueError, KeyError, TypeError) as exc:
            self._json({"error": str(exc)}, 400)
        finally:
            app.store.close()


def build_server(host="127.0.0.1", port=8765, root=".", desktop_token=None):
    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.root = root
    httpd.desktop_token = desktop_token
    return httpd


def serve(host="127.0.0.1", port=8765, root="."):
    httpd = build_server(host, port, root)
    print(f"PaperDigHelper UI: http://{host}:{httpd.server_address[1]}  (Ctrl-C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    args = sys.argv[1:]
    import os
    serve(
        port=int(args[0]) if args else int(os.environ.get("PAPERDIGHELPER_PORT", "8765")),
        root=os.environ.get("PAPERDIGHELPER_ROOT", "."),
    )

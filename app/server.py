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

from . import creation
from .language import language
from .service import App

STATIC = Path(__file__).resolve().parent / "static"
VERSION = "0.12"
JOBS = {}
JOBS_LOCK = threading.Lock()
JOB_SEQ = [0]
ORGANIZATION_JOB_LOCK = threading.Lock()
ORGANIZATION_PROCESSES_LOCK = threading.Lock()
ORGANIZATION_PROCESSES = set()
ORGANIZATION_STOPPING = threading.Event()


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
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
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
    project_id = project_id or app.get_default_project_id()
    project = app.projects.get_project(project_id) or {}
    return {"project": project.get("name") or project_id,
            "pinned": [term for term in app.profile(project_id)["pinned_terms"]
                       if isinstance(term, str) and 0 < len(term) <= 100][:40],
            "interest": [item["term"] for item in keywords(context(app, project_id), PROFILE_STOPWORDS)
                         if isinstance(item.get("term"), str) and 0 < len(item["term"]) <= 100][:40],
            "language": app.language()}


# Keys and budget ceilings are owned by the gateway, not the cosmetic settings file.
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


class Handler(BaseHTTPRequestHandler):
    server_version = "PaperDigHelper/0.6"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    def _app(self):
        return make_app(getattr(self.server, "root", "."))

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

    def _static(self, path):
        target = (STATIC / ("index.html" if path in ("/", "") else path.lstrip("/"))).resolve()
        if not str(target).startswith(str(STATIC)) or not target.is_file():
            self.send_error(404)
            return
        body = target.read_bytes()
        if target.suffix == ".html":
            body = re.sub(rb"(<head(?:\s[^>]*)?>)", lambda m: m.group(1) + I18N_SCRIPTS, body, count=1)
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

    def _body(self):
        length = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(length) or b"{}")

    # -------------------------------------------------------------------- GET
    def do_GET(self):
        if not self._desktop_access():
            return
        parsed = urlparse(self.path)
        route, query = parsed.path, parse_qs(parsed.query)
        requested_project = query.get("project_id", [None])[0]
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
        if route == "/api/organization":
            return self._organization()
        if route == "/api/home":
            app = self._app()
            # Extract project_id from query if provided
            project_id = query.get("project_id", [None])[0]
            self._json({"server_version": VERSION, "stats": app.stats(project_id),
                        "profile": app.profile(project_id),
                        "cards": app.cards(project_id=project_id), "summaries": app.store.summaries(),
                        "usage": app.usage(), "dev_mode": app.gateway.dev,
                        "provider": app.provider_status(),
                        "latest_jobs": list(JOBS.values())[-3:]})
        elif route == "/api/settings":
            app = self._app()
            self._json(self._settings_payload(app))
        elif route == "/api/state":  # kept for compatibility
            app = self._app()
            project_id = query.get("project_id", [None])[0]
            self._json({"profile": app.profile(project_id), "cards": app.cards(project_id=project_id)})
        elif route.startswith("/api/project-guidance/sessions/"):
            session_id = route.split("/")[-1]
            session = self._app().store.guidance_session(session_id)
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
            status = app.fulltext_status(key)
            if (query.get("text") or ["0"])[0] == "1":
                status["texts"] = app.store.fulltext_pages(key)
            self._json(status)
        elif route == "/api/figure-page":
            app = self._app()
            self._json({"page": app.figure_page((query.get("key") or [""])[0], (query.get("q") or [""])[0])})
        elif route == "/api/pdf/view":
            app = self._app()
            path = app.pdf_path((query.get("key") or [""])[0])
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
            project_id = query.get("project_id", [None])[0]
            # Export all project data
            data = {
                "exported_at": datetime.now().isoformat(),
                "profile": app.profile(project_id),
                "library": app.library(project_id),
                "stats": app.stats(project_id),
            }
            self._json(data)
        elif route == "/api/user_settings":
            # GET settings from file
            settings_file = Path(self._data()) / "settings.json"
            if settings_file.exists():
                settings = json.loads(settings_file.read_text())
            else:
                settings = {}
            # Provider keys live only in the gateway key file, never here.
            settings = {k: v for k, v in settings.items() if k not in USER_SETTINGS_EXCLUDED}
            self._json({"settings": settings})
        else:
            self._static(route)

    # ------------------------------------------------------------------- POST
    def do_POST(self):
        if not self._desktop_access():
            return
        if not self._same_origin():
            return self._json({"error": "cross-origin request denied"}, 403)
        route = urlparse(self.path).path
        if route in ("/api/organization", "/api/settings"):
            # These routes mutate the local library or store a credential: also cap the body.
            limit = 2_000_000 if route == "/api/organization" else 8_000
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                return self._json({"error": "invalid content length"}, 400)
            if length < 0 or length > limit:
                self.close_connection = True
                return self._json({"error": "request too large"}, 413)
        if route == "/api/seeds/pdf":
            return self._import_pdf()
        try:
            body = self._body()
        except (ValueError, json.JSONDecodeError):
            return self._json({"error": "invalid JSON"}, 400)
        if not isinstance(body, dict):
            return self._json({"error": "request must be an object"}, 400)
        if route == "/api/organization":
            if not isinstance(body, dict):
                return self._json({"error": "request must be an object"}, 400)
            return self._organization(body)
        if route == "/api/settings":
            if not isinstance(body, dict):
                return self._json({"error": "request must be an object"}, 400)
            app = self._app()
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
        if route == "/api/projects":
            # POST: create new project
            name = body.get("name")
            creation_mode = body.get("creation_mode", "manual")
            keywords = body.get("keywords", [])
            if not name:
                return self._json({"error": "name required"}, 400)
            try:
                result = app.create_project(name, creation_mode, keywords, body.get("seeds") or [],
                                            body.get("guidance_transcript"), body.get("learning_path"))
            except (ValueError, TypeError, sqlite3.IntegrityError) as exc:
                return self._json({"error": str(exc)}, 400)
            self._json(result)
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
                    self._json(app.seed_search(body.get("query")))
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
            try:
                if action == "turn":
                    self._json(app.guidance_turn(session_id, body.get("message"), bool(body.get("dry_run")),
                                                 retry=bool(body.get("retry")), draft_edits=body.get("draft")))
                elif action == "search":
                    self._json(app.guidance_search(session_id, body.get("query")))
                elif action == "preview":
                    self._json(app.guidance_preview(session_id, body.get("draft")))
                elif action == "finalize":
                    self._json(app.finalize_guidance(session_id, body.get("draft"), body.get("selected_keys")))
                else:
                    return self._json({"error": "unknown guidance action"}, 404)
            except (ValueError, TypeError) as exc:
                return self._json({"error": str(exc)}, 400)
        elif route == "/api/refresh":
            include_distractors = bool(body.get("distractors"))
            pages = int(body.get("pages", 1))
            project_id = body.get("project_id")
            job = _job_start("refresh", lambda: make_app(getattr(self.server, "root", ".")).refresh_candidates(
                pages=pages, include_distractors=include_distractors, project_id=project_id))
            self._json(job)
        elif route == "/api/daily":
            project_id = body.get("project_id")
            self._json(app.build_batch(limit=int(body.get("limit", 5)), project_id=project_id))
        elif route == "/api/triage":
            project_id = body.get("project_id")
            self._json(app.triage(app.cards(project_id=project_id), dry_run=bool(body.get("dry_run")), project_id=project_id))
        elif route == "/api/feedback":
            key, action = body.get("key"), body.get("action")
            if not key or not action:
                return self._json({"error": "key and action required"}, 400)
            project_id = body.get("project_id")
            try:
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
            self._json(app.save_fulltext(body.get("key") or "", body.get("pages") or []))
        elif route == "/api/qa":
            try:
                self._json(app.qa(body.get("key"), body.get("question") or "", body.get("selection"),
                                  image=body.get("image"), page_hint=body.get("page_hint"),
                                  context=body.get("context") or "normal", project_id=body.get("project_id"),
                                  dry_run=bool(body.get("dry_run"))))
            except (ValueError, TypeError) as exc:
                return self._json({"error": str(exc)}, 400)
        elif route == "/api/translate":
            self._json(app.translate(body.get("text") or "", dry_run=bool(body.get("dry_run"))))
        elif route == "/api/detail":
            # POST body avoids URL-encoding issues entirely; the UI uses this first.
            app = self._app()
            detail = app.paper_detail(body.get("key") or "", body.get("project_id"))
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
            settings_file.write_text(json.dumps(settings, indent=2))
            self._json({"status": "saved"})
        elif route == "/api/cache":
            # DELETE cache (via POST with _method: DELETE)
            if body.get("_method") == "DELETE":
                cache_dir = Path(self._data()) / "cache"
                if cache_dir.exists():
                    import shutil
                    shutil.rmtree(cache_dir)
                    cache_dir.mkdir(parents=True, exist_ok=True)
                self._json({"status": "cleared"})
            else:
                self._json({"error": "method not allowed"}, 405)
        else:
            self._json({"error": "unknown route"}, 404)

    def do_DELETE(self):
        if not self._desktop_access():
            return
        if not self._same_origin():
            return self._json({"error": "cross-origin request denied"}, 403)
        parsed = urlparse(self.path)
        route, query = parsed.path, parse_qs(parsed.query)
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
        if route.startswith("/api/project-guidance/sessions/"):
            try:
                return self._json(self._app().cancel_guidance(route.split("/")[-1]))
            except LookupError as exc:
                return self._json({"error": str(exc)}, 404)
            except ValueError as exc:
                return self._json({"error": str(exc)}, 409)
        return self._json({"error": "unknown route"}, 404)

    @staticmethod
    def _settings_payload(app):
        """Provider state, AI switch and the enforced ceilings; never the key itself."""
        limits = app.gateway.limits()
        return {"provider": app.provider_status(), "openalex": app.openalex_status(), "dev_mode": app.gateway.dev,
                "ai_enabled": app.gateway.enabled(), "usage": app.usage(),
                "limits": {k: limits[k] for k in ("daily_total_tokens", "monthly_total_tokens",
                                                   "daily_usd", "monthly_usd")}}

    def _list_projects(self):
        """GET /api/projects - list all projects"""
        app = self._app()
        projects = app.projects.list_projects()
        self._json({"projects": projects})

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
            if operation in {"suggest", "graph"}:
                path = app.store.path.resolve()
                request = {"profile": suggestion_profile(app, body.get("project_id"))} if operation == "suggest" else None
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

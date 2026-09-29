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
import sys
import threading
import traceback
import subprocess
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

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


def organization_job(db_path, project, operation="suggest"):
    """One bounded offline worker; no provider or user text on the command line."""
    from . import organization_worker  # also included by the desktop packager
    if not ORGANIZATION_JOB_LOCK.acquire(blocking=False):
        raise ValueError("已有分类任务正在运行")
    try:
        command = ([sys.executable, "--organization-worker"] if getattr(sys, "frozen", False)
                   else [sys.executable, "-m", "app.organization_worker"])
        with ORGANIZATION_PROCESSES_LOCK:
            if ORGANIZATION_STOPPING.is_set():
                raise ValueError("应用正在退出")
            process = subprocess.Popen(command + [str(db_path), project, str(os.getpid()), operation],
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                       cwd=str(Path(__file__).resolve().parents[1]))
            ORGANIZATION_PROCESSES.add(process)
        try:
            stdout, stderr = process.communicate(timeout=120)
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


def make_app(root="."):
    import os
    return App(root=root, data_dir=os.environ.get("PAPERDIGHELPER_DATA"))


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
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(str(target))[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
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

    def _body(self):
        length = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(length) or b"{}")

    # -------------------------------------------------------------------- GET
    def do_GET(self):
        if not self._desktop_access():
            return
        parsed = urlparse(self.path)
        route, query = parsed.path, parse_qs(parsed.query)
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
            self._json({"provider": app.provider_status(), "dev_mode": app.gateway.dev})
        elif route == "/api/state":  # kept for compatibility
            app = self._app()
            project_id = query.get("project_id", [None])[0]
            self._json({"profile": app.profile(project_id), "cards": app.cards(project_id=project_id)})
        elif route == "/api/paper":
            # Paper keys are URLs; prefer ?key= over a path segment.
            app = self._app()
            key = (query.get("key") or [""])[0]
            detail = app.paper_detail(key)
            if not detail:
                print(f"[404] paper key={key!r}", file=sys.stderr)
            self._json(detail or {"error": "not found", "key": key}, 200 if detail else 404)
        elif route.startswith("/api/paper/"):
            app = self._app()
            detail = app.paper_detail(unquote(route[len("/api/paper/"):]))
            self._json(detail or {"error": "not found"}, 200 if detail else 404)
        elif route.startswith("/api/jobs/"):
            self._json(_job_get(route[len("/api/jobs/"):]))
        elif route == "/api/library":
            app = self._app()
            project_id = query.get("project_id", [None])[0]
            self._json({"items": app.library(project_id), "stats": app.stats(project_id)})
        elif route == "/api/qa":
            app = self._app()
            self._json({"history": app.qa_history((query.get("key") or [""])[0])})
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
            self._json({"profile": app.profile(project_id), "versions": app.store.profile_versions()})
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
            settings_file = Path.home() / "Documents" / "PaperDigHelper" / "settings.json"
            if settings_file.exists():
                settings = json.loads(settings_file.read_text())
            else:
                settings = {}
            self._json({"settings": settings})
        else:
            self._static(route)

    # ------------------------------------------------------------------- POST
    def do_POST(self):
        if not self._desktop_access():
            return
        route = urlparse(self.path).path
        if route in ("/api/organization", "/api/settings"):
            # Same-origin only: these routes mutate the local library or store a credential.
            origin = self.headers.get("Origin")
            expected = "http://" + self.headers.get("Host", "")
            if origin and origin != expected:
                return self._json({"error": "cross-origin request denied"}, 403)
            limit = 2_000_000 if route == "/api/organization" else 8_000
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                return self._json({"error": "invalid content length"}, 400)
            if length < 0 or length > limit:
                self.close_connection = True
                return self._json({"error": "request too large"}, 413)
        try:
            body = self._body()
        except (ValueError, json.JSONDecodeError):
            return self._json({"error": "invalid JSON"}, 400)
        if route == "/api/organization":
            if not isinstance(body, dict):
                return self._json({"error": "request must be an object"}, 400)
            return self._organization(body)
        if route == "/api/settings":
            if not isinstance(body, dict):
                return self._json({"error": "request must be an object"}, 400)
            app = self._app()
            try:
                status = app.clear_api_key() if body.get("clear") else app.save_api_key(body.get("api_key") or "")
            except ValueError as exc:
                return self._json({"error": str(exc)}, 400)
            return self._json({"provider": status, "dev_mode": app.gateway.dev})
        app = self._app()
        if route == "/api/projects":
            # POST: create new project
            name = body.get("name")
            creation_mode = body.get("creation_mode", "manual")
            keywords = body.get("keywords", [])
            if not name:
                return self._json({"error": "name required"}, 400)
            project_id = app.projects.create_project(name, creation_mode, keywords)
            self._json({"project_id": project_id, "name": name})
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
            self._json(app.record_feedback(key, action, body.get("reason"), project_id))
        elif route == "/api/undo":
            self._json(app.undo_feedback(int(body["feedback_id"])))
        elif route == "/api/unsave":
            self._json(app.unsave(body["key"]))
        elif route == "/api/pin":
            project_id = body.get("project_id")
            data = app.store.current_profile() or {"project": "world-models", "weights": {"pos": 1.0, "neg": 0.5}}
            data["pinned_terms"] = [t.strip() for t in (body.get("terms") or "").split(",") if t.strip()]
            app.save_profile(data, note="pin")
            self._json({"profile": app.profile(project_id), "stats": app.stats(project_id)})
        elif route == "/api/library":
            app = self._app()
            project_id = body.get("project_id")
            self._json({"items": app.library(project_id), "stats": app.stats(project_id)})
        elif route == "/api/fulltext":
            self._json(app.save_fulltext(body.get("key") or "", body.get("pages") or []))
        elif route == "/api/qa":
            self._json(app.qa(body.get("key"), body.get("question") or "", body.get("selection"),
                              image=body.get("image"), page_hint=body.get("page_hint"),
                              context=body.get("context") or "normal",
                              dry_run=bool(body.get("dry_run"))))
        elif route == "/api/translate":
            self._json(app.translate(body.get("text") or "", dry_run=bool(body.get("dry_run"))))
        elif route == "/api/detail":
            # POST body avoids URL-encoding issues entirely; the UI uses this first.
            app = self._app()
            detail = app.paper_detail(body.get("key") or "")
            if not detail:
                print(f"[404] paper key={body.get('key')!r} (POST)", file=sys.stderr)
            self._json(detail or {"error": "not found", "key": body.get("key")}, 200 if detail else 404)
        elif route == "/api/pdf/prepare":
            self._json(app.download_pdf(body["key"]))
        elif route == "/api/pdf":
            self._json(app.download_pdf(body["key"]))
        elif route == "/api/weekly_report/analysis":
            # Optional AI analysis for weekly report
            from .weekly_report import generate_weekly_report
            project_id = body.get("project_id")
            if not project_id:
                return self._json({"error": "project_id required"}, 400)
            # Return placeholder - actual AI analysis would consume tokens
            self._json({
                "analysis": "AI 分析功能需要启用 API 并消耗 token。请在设置中配置 API 密钥后使用。",
                "note": "这是一个占位符。完整实现将调用 gateway.call() 生成个性化分析。"
            })
        elif route == "/api/user_settings":
            # POST: save settings
            settings_file = Path.home() / "Documents" / "PaperDigHelper" / "settings.json"
            settings_file.parent.mkdir(parents=True, exist_ok=True)
            settings_file.write_text(json.dumps(body.get("settings", {}), indent=2))
            self._json({"status": "saved"})
        elif route == "/api/cache":
            # DELETE cache (via POST with _method: DELETE)
            if body.get("_method") == "DELETE":
                cache_dir = Path.home() / "Documents" / "PaperDigHelper" / "cache"
                if cache_dir.exists():
                    import shutil
                    shutil.rmtree(cache_dir)
                    cache_dir.mkdir(parents=True, exist_ok=True)
                self._json({"status": "cleared"})
            else:
                self._json({"error": "method not allowed"}, 405)
        else:
            self._json({"error": "unknown route"}, 404)

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
                job = _job_start("organization", lambda: organization_job(path, "default", operation))
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

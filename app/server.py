#!/usr/bin/env python3
"""Local loopback HTTP API + static UI. Binds 127.0.0.1 only.

Threaded so a slow fetch or model call cannot freeze the whole page. Each
request uses its own short-lived App (and therefore its own SQLite connection),
which keeps storage thread-safe without sharing a connection across threads.
Long operations (refresh) run as background jobs the page can poll.
"""
import json
import mimetypes
import sys
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from .service import App

STATIC = Path(__file__).resolve().parent / "static"
VERSION = "0.4"
JOBS = {}
JOBS_LOCK = threading.Lock()
JOB_SEQ = [0]


def make_app(root="."):
    return App(root=root)


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
    server_version = "PaperDigHelper/0.2"
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

    def _body(self):
        length = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(length) or b"{}")

    # -------------------------------------------------------------------- GET
    def do_GET(self):
        parsed = urlparse(self.path)
        route, query = parsed.path, parse_qs(parsed.query)
        if route == "/api/home":
            app = self._app()
            self._json({"server_version": VERSION, "stats": app.stats(), "profile": app.profile(),
                        "cards": app.cards(), "summaries": app.store.summaries(),
                        "latest_jobs": list(JOBS.values())[-3:]})
        elif route == "/api/state":  # kept for compatibility
            app = self._app()
            self._json({"profile": app.profile(), "cards": app.cards()})
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
            self._json({"items": app.library(), "stats": app.stats()})
        elif route == "/api/qa":
            app = self._app()
            self._json({"history": app.qa_history((query.get("key") or [""])[0])})
        elif route == "/api/fulltext":
            app = self._app()
            self._json(app.fulltext_status((query.get("key") or [""])[0]))
        elif route == "/api/pdf/view":
            app = self._app()
            path = app.pdf_path((query.get("key") or [""])[0])
            if path:
                self._file(path, "application/pdf")
            else:
                self._json({"error": "pdf not downloaded yet"}, 404)
        elif route == "/api/profile":
            app = self._app()
            self._json({"profile": app.profile(), "versions": app.store.profile_versions()})
        else:
            self._static(route)

    # ------------------------------------------------------------------- POST
    def do_POST(self):
        route = urlparse(self.path).path
        try:
            body = self._body()
        except (ValueError, json.JSONDecodeError):
            return self._json({"error": "invalid JSON"}, 400)
        app = self._app()
        if route == "/api/refresh":
            include_distractors = bool(body.get("distractors"))
            pages = int(body.get("pages", 1))
            job = _job_start("refresh", lambda: make_app(getattr(self.server, "root", ".")).refresh_candidates(
                pages=pages, include_distractors=include_distractors))
            self._json(job)
        elif route == "/api/daily":
            self._json(app.build_batch(limit=int(body.get("limit", 5))))
        elif route == "/api/triage":
            self._json(app.triage(app.cards(), dry_run=bool(body.get("dry_run"))))
        elif route == "/api/feedback":
            key, action = body.get("key"), body.get("action")
            if not key or not action:
                return self._json({"error": "key and action required"}, 400)
            self._json(app.record_feedback(key, action, body.get("reason")))
        elif route == "/api/undo":
            self._json(app.undo_feedback(int(body["feedback_id"])))
        elif route == "/api/unsave":
            self._json(app.unsave(body["key"]))
        elif route == "/api/pin":
            data = app.store.current_profile() or {"project": "world-models", "weights": {"pos": 1.0, "neg": 0.5}}
            data["pinned_terms"] = [t.strip() for t in (body.get("terms") or "").split(",") if t.strip()]
            app.save_profile(data, note="pin")
            self._json({"profile": app.profile(), "stats": app.stats()})
        elif route == "/api/library":
            app = self._app()
            self._json({"items": app.library(), "stats": app.stats()})
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
        else:
            self._json({"error": "unknown route"}, 404)


def build_server(host="127.0.0.1", port=8765, root="."):
    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.root = root
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
    serve(port=int(args[0]) if args else 8765)

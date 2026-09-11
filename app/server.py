#!/usr/bin/env python3
"""Local loopback HTTP API + static UI. Binds 127.0.0.1 only.

Tauri (or a browser) loads this UI; all state stays in the local SQLite file.
"""
import json
import mimetypes
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .service import App

STATIC = Path(__file__).resolve().parent / "static"


class Handler(BaseHTTPRequestHandler):
    app = None
    server_version = "PaperDigHelper/0.1"

    def log_message(self, fmt, *args):  # keep the console quiet
        pass

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

    def _body(self):
        length = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(length) or b"{}")

    def do_GET(self):
        route = urlparse(self.path).path
        if route == "/api/state":
            self._json({"profile": self.app.profile(), "cards": self.app.cards(),
                        "has_batch": bool(self.app.store.latest_batch())})
        elif route == "/api/profile":
            self._json({"profile": self.app.profile(), "versions": self.app.store.profile_versions()})
        else:
            self._static(route)

    def do_POST(self):
        route = urlparse(self.path).path
        try:
            body = self._body()
        except (ValueError, json.JSONDecodeError):
            return self._json({"error": "invalid JSON"}, 400)
        if route == "/api/refresh":
            self._json(self.app.refresh_candidates(pages=int(body.get("pages", 1))))
        elif route == "/api/daily":
            self._json(self.app.build_batch(limit=int(body.get("limit", 5))))
        elif route == "/api/triage":
            self._json(self.app.triage(self.app.cards(), dry_run=bool(body.get("dry_run"))))
        elif route == "/api/feedback":
            key, action = body.get("key"), body.get("action")
            if not key or not action:
                return self._json({"error": "key and action required"}, 400)
            self._json(self.app.record_feedback(key, action, body.get("reason")))
        elif route == "/api/undo":
            self._json(self.app.undo_feedback(int(body["feedback_id"])))
        elif route == "/api/pin":
            data = self.app.store.current_profile() or {"project": "world-models", "weights": {"pos": 1.0, "neg": 0.5}}
            data["pinned_terms"] = [t.strip() for t in (body.get("terms") or "").split(",") if t.strip()]
            self.app.save_profile(data, note="pin")
            self._json({"profile": self.app.profile()})
        elif route == "/api/pdf":
            self._json(self.app.download_pdf(body["key"]))
        else:
            self._json({"error": "unknown route"}, 404)


def build_server(host="127.0.0.1", port=8765, root="."):
    """Single-threaded local server: one user, and it keeps the SQLite connection on one thread."""
    Handler.app = App(root=root)
    return HTTPServer((host, port), Handler)


def serve(host="127.0.0.1", port=8765, root="."):
    httpd = build_server(host, port, root)
    actual_port = httpd.server_address[1]
    print(f"PaperDigHelper UI: http://{host}:{actual_port}  (Ctrl-C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    args = sys.argv[1:]
    serve(port=int(args[0]) if args else 8765)

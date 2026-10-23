"""Owned loopback server for the desktop shell (macOS, Windows)."""
import json
import os
import secrets
import shutil
import sys
import threading
from pathlib import Path

from . import maintenance, platform_compat
from .server import build_server, stop_organization_workers
from .service import App


LOG_LIMIT_BYTES = 1_000_000


def redirect_stderr_to_log(root, limit=LOG_LIMIT_BYTES):
    """Send stderr to <data>/logs/backend.log (size-capped: one rotated copy). The Windows shell has no console
    to inherit, so it sets PDH_LOG_STDERR=1. Only what the backend itself prints reaches stderr: the HTTP
    server's per-request log is silenced, so request paths (and the desktop token in them) are not logged."""
    logs = Path(root) / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    path = logs / "backend.log"
    try:
        if path.stat().st_size > limit:
            os.replace(path, logs / "backend.log.1")
    except FileNotFoundError:
        pass
    sys.stderr = path.open("a", encoding="utf-8", errors="replace", buffering=1)
    return path


def main():
    platform_compat.force_utf8_std_streams()
    if sys.argv[1:2] == ["--organization-worker"]:
        from .organization_worker import main as run_worker
        return run_worker(sys.argv[2:])
    resources = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    configured_data = os.environ.get("PAPERDIGHELPER_DATA")
    root = (Path(configured_data).expanduser().resolve() if configured_data else
            platform_compat.default_data_dir())
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    harness = root / "harness"
    harness.mkdir(exist_ok=True)
    shutil.copyfile(resources / "harness" / "budget.json", harness / "budget.json")
    seeds = harness / "seeds.json"
    bundled_seeds = resources / "harness" / "seeds.json"
    if bundled_seeds.exists() and (not seeds.exists() or seeds.stat().st_size < 100):
        shutil.copyfile(bundled_seeds, seeds)
    os.environ["PAPERDIGHELPER_DATA"] = str(root)
    if os.environ.get("PDH_LOG_STDERR") == "1":
        redirect_stderr_to_log(root)
    os.chdir(root)
    with (root / ".desktop.lock").open("a", encoding="utf-8") as lock:
        try:
            platform_compat.lock_exclusive(lock, blocking=False)
        except BlockingIOError:
            raise SystemExit("PaperDigHelper is already running.")
        httpd = build_server(port=0, root=resources, desktop_token=secrets.token_hex(32))

        def bootstrap():
            try:
                app = App(root=resources, data_dir=root)
                if not app.store.papers():
                    app.ensure_seed_papers()
                    maintenance.manual_refresh(app, pages=1, per_page=100)
                app.store.conn.close()
            except Exception as exc:
                print(f"PDH_BOOTSTRAP_FAILED {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)

        threading.Thread(target=bootstrap, daemon=True).start()

        def watch_parent():
            sys.stdin.buffer.read()
            stop_organization_workers()
            httpd.shutdown()

        threading.Thread(target=watch_parent, daemon=True).start()
        print(f"PDH_READY http://127.0.0.1:{httpd.server_port}/_desktop/{httpd.desktop_token}", flush=True)
        try:
            httpd.serve_forever(poll_interval=0.1)
        finally:
            stop_organization_workers()
            httpd.server_close()

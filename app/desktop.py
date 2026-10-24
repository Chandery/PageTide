"""Owned loopback server for the desktop shell (macOS, Windows)."""
import json
import os
import secrets
import shutil
import sys
import threading
from pathlib import Path

from . import platform_compat, updater
from .server import build_server, stop_organization_workers


LOG_LIMIT_BYTES = 1_000_000


class SizeCappedLog:
    """Text stream for stderr that rotates <log> to <log>.1 once about `limit` bytes were written (also while the
    process keeps running). Rotation is best effort: if the file cannot be replaced (Windows: held by another
    process) it is truncated, and if that fails too the stream keeps appending. It never raises into the caller."""
    encoding = "utf-8"
    errors = "replace"

    def __init__(self, path, limit=LOG_LIMIT_BYTES):
        self.path, self.limit = Path(path), limit
        self.handle, self.written = None, 0
        self._open(rotate_if_large=True)

    def _open(self, rotate_if_large=False):
        try:
            size = self.path.stat().st_size
        except OSError:
            size = 0
        if rotate_if_large and size > self.limit:
            size = self._rotate(size)
        self.written = size
        self.handle = self.path.open("a", encoding="utf-8", errors="replace", buffering=1)

    def _rotate(self, size):
        try:
            os.replace(self.path, self.path.with_name(self.path.name + ".1"))
            return 0
        except OSError:
            try:
                self.path.write_bytes(b"")   # cannot rotate: at least cap the growth
                return 0
            except OSError:
                return size

    def write(self, text):
        try:
            if self.written + len(text) > self.limit and self.written:
                self.handle.close()
                self._open(rotate_if_large=True)
            self.handle.write(text)
            self.written += len(text.encode("utf-8", "replace"))
        except (OSError, ValueError):
            pass
        return len(text)

    def flush(self):
        try:
            self.handle.flush()
        except (OSError, ValueError):
            pass

    def isatty(self):
        return False

    def writable(self):
        return True

    def close(self):
        try:
            self.handle.close()
        except OSError:
            pass


def redirect_stderr_to_log(root, limit=LOG_LIMIT_BYTES):
    """Send stderr to <data>/logs/backend.log (size-capped: one rotated copy). The Windows shell has no console
    to inherit, so it sets PDH_LOG_STDERR=1. Only what the backend itself prints reaches stderr: the HTTP
    server's per-request log is silenced, so request paths (and the desktop token in them) are not logged."""
    logs = Path(root) / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    sys.stderr = SizeCappedLog(logs / "backend.log", limit)
    return logs / "backend.log"


def on_parent_gone(httpd):
    """The shell closed our stdin (it is quitting). An update the user asked for starts first: the shell kills this
    backend two seconds after closing stdin, and the helper does not depend on us (macOS: it waits for the shell's
    pid; Windows: the installer checks for the running app itself)."""
    updater.run_pending()
    stop_organization_workers()
    httpd.shutdown()


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
    os.environ["PAPERDIGHELPER_DATA"] = str(root)
    os.chdir(root)
    with (root / ".desktop.lock").open("a", encoding="utf-8") as lock:
        try:
            platform_compat.lock_exclusive(lock, blocking=False)
        except BlockingIOError:
            raise SystemExit("PaperDigHelper is already running.")
        # After the lock: a second instance must say "already running", not fail on a log another backend holds.
        if os.environ.get("PDH_LOG_STDERR") == "1":
            redirect_stderr_to_log(root)
        if os.environ.get("PDH_APP_VERSION"):
            updater.Updater(root, os.environ["PDH_APP_VERSION"]).startup_cleanup()
        httpd = build_server(port=0, root=resources, desktop_token=secrets.token_hex(32))

        def watch_parent():
            sys.stdin.buffer.read()
            on_parent_gone(httpd)

        threading.Thread(target=watch_parent, daemon=True).start()
        print(f"PDH_READY http://127.0.0.1:{httpd.server_port}/_desktop/{httpd.desktop_token}", flush=True)
        try:
            httpd.serve_forever(poll_interval=0.1)
        finally:
            stop_organization_workers()
            httpd.server_close()

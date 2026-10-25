"""Owned loopback server for the desktop shell (macOS, Windows)."""
import json
import os
import secrets
import shutil
import sys
import threading
from pathlib import Path

from . import data_location, platform_compat, updater
from .server import build_server, clean_legacy_default_project, stop_organization_workers


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
    to inherit, so it sets PAGETIDE_LOG_STDERR=1. Only what the backend itself prints reaches stderr: the HTTP
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


def choose_data_root(environ):
    """The library folder for this start, recorded in `environ` for the settings page: PAGETIDE_DATA_SOURCE is "env"
    (PAGETIDE_DATA chose it; the page cannot move it), "default" or "moved" (data_location's pointer in the default
    folder); PAGETIDE_DATA_MISSING names a moved-to folder that was not found this time."""
    configured = environ.get("PAGETIDE_DATA")
    default = platform_compat.default_data_dir(environ)
    if configured:
        root, source, missing = Path(configured).expanduser().resolve(), "env", None
    else:
        root, missing = data_location.resolve(default)
        source = "default" if root == default else "moved"
    environ.update(PAGETIDE_DATA_SOURCE=source, PAGETIDE_DEFAULT_DATA=str(default))
    if missing:
        environ["PAGETIDE_DATA_MISSING"] = missing
    return root


def main():
    platform_compat.force_utf8_std_streams()
    platform_compat.add_bundled_ca_certificates()
    if sys.argv[1:2] == ["--organization-worker"]:
        from .organization_worker import main as run_worker
        return run_worker(sys.argv[2:])
    resources = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    root = choose_data_root(os.environ)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    (root / "app").mkdir(exist_ok=True)
    shutil.copyfile(resources / "app" / "budget.json", root / "app" / "budget.json")
    os.environ["PAGETIDE_DATA"] = str(root)
    os.chdir(root)
    with (root / ".desktop.lock").open("a", encoding="utf-8") as lock:
        try:
            platform_compat.lock_exclusive(lock, blocking=False)
        except BlockingIOError:
            raise SystemExit("PageTide is already running.")
        # After the lock: a second instance must say "already running", not fail on a log another backend holds.
        if os.environ.get("PAGETIDE_LOG_STDERR") == "1":
            redirect_stderr_to_log(root)
        if os.environ.get("PAGETIDE_APP_VERSION"):
            updater.Updater(root, os.environ["PAGETIDE_APP_VERSION"]).startup_cleanup()
        if os.environ.get("PAGETIDE_APP_VERSION") or os.environ.get("PAGETIDE_LEGACY_CLEANUP") == "1":
            clean_legacy_default_project(resources)   # once per library; holds the instance lock, no request is served yet
        httpd = build_server(port=0, root=resources, desktop_token=secrets.token_hex(32))

        def watch_parent():
            sys.stdin.buffer.read()
            on_parent_gone(httpd)

        threading.Thread(target=watch_parent, daemon=True).start()
        print(f"PAGETIDE_READY http://127.0.0.1:{httpd.server_port}/_desktop/{httpd.desktop_token}", flush=True)
        try:
            httpd.serve_forever(poll_interval=0.1)
        finally:
            stop_organization_workers()
            httpd.server_close()

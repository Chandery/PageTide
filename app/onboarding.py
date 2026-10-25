"""When the onboarding tour is offered: once after the app is first installed, and again only after a reinstall that
finds no project.

State lives in <data>/onboarding.json, not in settings.json: the settings page saves a whole file and would wipe it.
{"seen_version": "0.1.0", "completed_at": "...", "install_id": "..."}. Skipping and finishing the tour are the same act
(mark_done). An app update is not a reinstall question: with a project the tour stays away; the settings page can
replay it. The server decides the version and the install itself; a page cannot claim either.
"""
import json
import os
import sys
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path

from . import app_version

FILE = "onboarding.json"
_LOCK = threading.Lock()
_EMPTY = {"seen_version": None, "completed_at": None, "install_id": None}


def install_id():
    """Which installed copy of the app is running. The data folder outlives an uninstall, so a reinstall is told apart
    by the executable itself: a new copy is a new file (inode / file index) with its own build time. A source run has
    no installed copy and is always the same one."""
    if not getattr(sys, "frozen", False):
        return "source"
    try:
        stat = os.stat(sys.executable)
    except OSError:
        return "unknown"
    return f"{stat.st_ino}:{stat.st_mtime_ns}"


def read(data_dir):
    try:
        value = json.loads((Path(data_dir) / FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return dict(_EMPTY)
    if not isinstance(value, dict):
        return dict(_EMPTY)
    return {key: value.get(key) if isinstance(value.get(key), str) else None for key in _EMPTY}


def state(data_dir, root, project_count):
    """Whether the page should offer the tour now. `reason` is for the page's logic, never shown to the person."""
    version = app_version.current(root)
    saved = read(data_dir)
    if saved["completed_at"] is None and saved["seen_version"] is None:
        show, reason = True, "first_run"
    elif project_count == 0 and saved["install_id"] != install_id():
        show, reason = True, "reinstalled"
    else:
        show, reason = False, "seen"
    return {"show": show, "reason": reason, "version": version, "seen_version": saved["seen_version"],
            "completed_at": saved["completed_at"], "project_count": project_count}


def mark_done(data_dir, root, now=None):
    """Remember that the tour was seen (finished or skipped) on this install. Atomic; returns the stored state."""
    directory = Path(data_dir)
    directory.mkdir(parents=True, exist_ok=True)
    value = {"seen_version": app_version.current(root),
             "completed_at": (now or datetime.now(timezone.utc)).replace(microsecond=0).isoformat(),
             "install_id": install_id()}
    with _LOCK:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=directory, delete=False, suffix=".tmp") as staged:
            temporary = Path(staged.name)
            json.dump(value, staged)
            staged.flush()
            os.fsync(staged.fileno())
        try:
            os.replace(temporary, directory / FILE)
        finally:
            temporary.unlink(missing_ok=True)
    return value

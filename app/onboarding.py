"""When the onboarding tour is offered: first launch (no project yet) and again after each app update.

State lives in <data>/onboarding.json, not in settings.json: the settings page saves a whole file and would wipe it.
{"seen_version": "0.1.0", "completed_at": "..."}. Skipping and finishing the tour are the same act (mark_done). The server
decides the version itself; a page cannot claim a version it did not see.
"""
import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path

from . import app_version

FILE = "onboarding.json"
_LOCK = threading.Lock()


def read(data_dir):
    try:
        value = json.loads((Path(data_dir) / FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"seen_version": None, "completed_at": None}
    if not isinstance(value, dict):
        return {"seen_version": None, "completed_at": None}
    seen, done = value.get("seen_version"), value.get("completed_at")
    return {"seen_version": seen if isinstance(seen, str) else None, "completed_at": done if isinstance(done, str) else None}


def state(data_dir, root, project_count):
    """Whether the page should offer the tour now. `reason` is for the page's logic, never shown to the person."""
    version = app_version.current(root)
    saved = read(data_dir)
    if project_count == 0:
        show, reason = True, "no_project"
    elif saved["seen_version"] != version:
        show, reason = True, "new_version"
    else:
        show, reason = False, "seen"
    return {"show": show, "reason": reason, "version": version, "seen_version": saved["seen_version"],
            "completed_at": saved["completed_at"], "project_count": project_count}


def mark_done(data_dir, root, now=None):
    """Remember that this version's tour was seen (finished or skipped). Atomic; returns the stored state."""
    directory = Path(data_dir)
    directory.mkdir(parents=True, exist_ok=True)
    value = {"seen_version": app_version.current(root),
             "completed_at": (now or datetime.now(timezone.utc)).replace(microsecond=0).isoformat()}
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

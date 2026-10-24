"""The version of the running app, for the onboarding tour (it is shown again after an update).

The desktop shell passes PDH_APP_VERSION (src-tauri/src/main.rs). A source checkout has no such variable, so it falls back to
the version in src-tauri/tauri.conf.json next to the code, and to "unknown" when neither is there. The check in
app/updater.py keeps its own rule (no variable means a development build) and is not affected by this fallback.
"""
import json
import os
import re
from pathlib import Path

UNKNOWN = "unknown"
_VERSION = re.compile(r"^\d+\.\d+\.\d+([-+][0-9A-Za-z.-]+)?$")


def _valid(value):
    return value if isinstance(value, str) and _VERSION.match(value) else None


def current(root="."):
    """PDH_APP_VERSION, else the `version` of <root>/src-tauri/tauri.conf.json, else "unknown". Only well-formed versions count."""
    found = _valid(os.environ.get("PDH_APP_VERSION"))
    if found:
        return found
    try:
        config = json.loads((Path(root) / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return UNKNOWN
    return _valid(config.get("version") if isinstance(config, dict) else None) or UNKNOWN

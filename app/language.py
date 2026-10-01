"""Interface language chosen on the settings page (settings.json in the data directory).

Chinese is the source language. "en-US" switches the UI language pack, the prose the
server writes, and the language AI replies are written in. Anything missing or
unreadable means Chinese, so the default path never depends on this file.
"""
import json
from pathlib import Path

SUPPORTED = ("zh-CN", "en-US")


def language(data_dir):
    try:
        value = json.loads((Path(data_dir) / "settings.json").read_text(encoding="utf-8")).get("language")
    except (OSError, ValueError, AttributeError):
        return "zh-CN"
    return value if value in SUPPORTED else "zh-CN"

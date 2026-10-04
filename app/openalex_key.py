"""Optional OpenAlex API key: a free key raises the daily allowance of the public metadata API.

Stored in its own file inside the data directory (0600), never in settings.json, never echoed.
It is sent only as an Authorization header to api.openalex.org (see sources.OpenAlex._request).
"""
import os
import re
from pathlib import Path

KEY_FILE_NAME = "openalex.key"
ENV_VAR = "OPENALEX_API_KEY"
_PREFIX = "OPENALEX_API_KEY="


def key_file(data_dir):
    return Path(data_dir) / KEY_FILE_NAME


def valid(value):
    return isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9._~-]{8,256}", value) is not None


def _read(path):
    try:
        for line in Path(path).read_text().splitlines():
            if line.startswith(_PREFIX):
                value = line[len(_PREFIX):].strip()
                if valid(value):
                    return value
    except OSError:
        pass
    return None


def load(data_dir):
    env = (os.environ.get(ENV_VAR) or "").strip()
    return env if valid(env) else _read(key_file(data_dir))


def status(data_dir):
    """Configured state for the UI; never the key."""
    env = (os.environ.get(ENV_VAR) or "").strip()
    if valid(env):
        return {"configured": True, "source": "environment"}
    if _read(key_file(data_dir)):
        return {"configured": True, "source": str(key_file(data_dir))}
    return {"configured": False, "source": None}


def save(data_dir, value):
    value = value.strip() if isinstance(value, str) else value
    if not valid(value):
        raise ValueError("OpenAlex 密钥格式无效")
    target = key_file(data_dir)
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    handle = os.open(str(target), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(handle, "w") as out:
        out.write(f"{_PREFIX}{value}\n")
    try:
        os.chmod(target, 0o600)
    except OSError:
        pass
    return status(data_dir)


def clear(data_dir):
    try:
        key_file(data_dir).unlink()
    except FileNotFoundError:
        pass
    return status(data_dir)

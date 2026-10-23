"""API keys of the paper sources that use one (SourceInfo.key is "optional" or "required").

One 0600 file per source inside the data directory (`<source id>.key`, e.g. openalex.key, baidu_scholar.key); never
settings.json, never echoed, never part of a URL, a cache name, a log line or an error. An environment variable
(SourceInfo.key_env) overrides the file. The file holds one `<KEY_ENV>=<key>` line, the format the OpenAlex key file has
always had. Each key is sent only as an Authorization header to its own provider's https host (see the adapters).
"""
import os
import re
from pathlib import Path

from . import source_adapters


def _info(source_id):
    info = source_adapters.info(source_id)
    return info if info is not None and info.key != "none" else None


def key_file(data_dir, source_id):
    if _info(source_id) is None:
        raise ValueError("该数据源没有密钥")
    return Path(data_dir) / f"{source_id}.key"


def valid(source_id, value):
    info = _info(source_id)
    return info is not None and isinstance(value, str) and re.fullmatch(info.key_pattern, value) is not None


def _read(info, path):
    prefix = f"{info.key_env}="
    try:
        for line in Path(path).read_text().splitlines():
            if line.startswith(prefix):
                value = line[len(prefix):].strip()
                if valid(info.id, value):
                    return value
    except OSError:
        pass
    return None


def load(data_dir, source_id):
    info = _info(source_id)
    if info is None:
        return None
    env = (os.environ.get(info.key_env) or "").strip()
    return env if valid(source_id, env) else _read(info, key_file(data_dir, source_id))


def status(data_dir, source_id):
    """Configured state for the UI; never the key."""
    info = _info(source_id)
    if info is None:
        return {"configured": False, "source": None}
    env = (os.environ.get(info.key_env) or "").strip()
    if valid(source_id, env):
        return {"configured": True, "source": "environment"}
    path = key_file(data_dir, source_id)
    if _read(info, path):
        return {"configured": True, "source": str(path)}
    return {"configured": False, "source": None}


def save(data_dir, source_id, value):
    info = _info(source_id)
    if info is None:
        raise ValueError("该数据源没有密钥")
    value = value.strip() if isinstance(value, str) else value
    if not valid(source_id, value):
        raise ValueError(f"{info.provider.split('（')[0]} 密钥格式无效")
    target = key_file(data_dir, source_id)
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    staged = target.with_name(target.name + ".tmp")
    handle = os.open(str(staged), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(handle, "w") as out:
        out.write(f"{info.key_env}={value}\n")
    os.chmod(staged, 0o600)
    os.replace(staged, target)
    return status(data_dir, source_id)


def clear(data_dir, source_id):
    info = _info(source_id)
    if info is not None:
        try:
            key_file(data_dir, source_id).unlink()
        except FileNotFoundError:
            pass
    return status(data_dir, source_id)

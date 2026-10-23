"""Optional OpenAlex API key: a free key raises the daily allowance of the public metadata API.

Kept as a thin wrapper over app/source_keys.py (one key file per source); the file format and name (openalex.key) are
unchanged. Stored in its own file inside the data directory (0600), never in settings.json, never echoed. It is sent only
as an Authorization header to api.openalex.org (see sources.OpenAlex._request).
"""
from . import source_keys

SOURCE_ID = "openalex"
KEY_FILE_NAME = "openalex.key"
ENV_VAR = "OPENALEX_API_KEY"


def key_file(data_dir):
    return source_keys.key_file(data_dir, SOURCE_ID)


def valid(value):
    return source_keys.valid(SOURCE_ID, value)


def load(data_dir):
    return source_keys.load(data_dir, SOURCE_ID)


def status(data_dir):
    """Configured state for the UI; never the key."""
    return source_keys.status(data_dir, SOURCE_ID)


def save(data_dir, value):
    return source_keys.save(data_dir, SOURCE_ID, value)


def clear(data_dir):
    return source_keys.clear(data_dir, SOURCE_ID)

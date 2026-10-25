"""Where the library lives, and moving it to a folder the person chooses.

The default folder (platform_compat.default_data_dir) always exists and holds `location.json`, {"data_dir": "<abs>"},
when the library lives elsewhere. The desktop backend reads it at start (resolve). Moving copies the whole library into
the new folder while the app runs (SQLite files through the online backup API, so each copy is consistent), checks the
copy, then points location.json at it; the app restarts to use it. The old folder is left exactly as it was, as a
backup the person can delete later. A folder that already holds a PageTide library is used as it is, never overwritten.
An environment-chosen folder (PAGETIDE_DATA) cannot be moved from the app.
"""
import json
import os
import shutil
import sqlite3
import tempfile
import uuid
from pathlib import Path

POINTER = "location.json"
LIBRARY_MARK = "pagetide.sqlite"
SUBFOLDER = "PageTide"            # used inside a chosen folder that already holds other files
SKIP_NAMES = {".desktop.lock", POINTER, "operation-locks"}
SKIP_SUFFIXES = ("-wal", "-shm", "-journal")
SQLITE_SUFFIXES = (".sqlite", ".sqlite3", ".db")
RETRIES = 3


class MoveError(RuntimeError):
    """A move that did not happen. `reason` is a short code the settings page turns into a sentence."""

    def __init__(self, reason, detail=""):
        super().__init__(detail or reason)
        self.reason = reason


def _pointer(default_dir):
    return Path(default_dir) / POINTER


def _read(default_dir):
    try:
        value = json.loads(_pointer(default_dir).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in value.items() if isinstance(v, str) and Path(v).is_absolute()} if isinstance(value, dict) else {}


def read_pointer(default_dir):
    return _read(default_dir).get("data_dir")


def write_pointer(default_dir, data_dir, previous=None):
    """Point the default folder at `data_dir` (atomic) and remember `previous`, the folder the library left, so the
    settings page can offer to delete it. Pointing at the default folder itself keeps only `previous`."""
    default_dir = Path(default_dir)
    value = {} if Path(data_dir).resolve() == default_dir.resolve() else {"data_dir": str(Path(data_dir).resolve())}
    if previous:
        value["previous"] = str(Path(previous).resolve())
    if not value:
        _pointer(default_dir).unlink(missing_ok=True)
        return
    default_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=default_dir, delete=False, suffix=".tmp") as staged:
        json.dump(value, staged)
        staged.flush()
        os.fsync(staged.fileno())
    os.replace(staged.name, _pointer(default_dir))


def previous(default_dir, current):
    """The folder the library was moved away from, while it still holds that old copy; None otherwise."""
    old = _read(default_dir).get("previous")
    if not old or not _is_library(old):
        return None
    if Path(old).resolve() == Path(current).resolve() or _inside(current, old) or _inside(old, current):
        return None
    return old


def remove_previous(default_dir, current):
    """Delete the old copy `previous` names: everything in that folder except the pointer (the default folder must
    keep it to find the library); the folder itself stays. Returns the folder that was emptied."""
    old = previous(default_dir, current)
    if not old:
        raise MoveError("no_previous")
    old = Path(old)
    keep = _pointer(default_dir).resolve()
    for child in list(old.iterdir()):
        if child.resolve() == keep:
            continue
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink()
    write_pointer(default_dir, current)          # forget it: nothing is left to offer
    return str(old)


def resolve(default_dir):
    """(folder to use, folder the pointer named but could not be found or None). A missing target (an unplugged
    drive, a deleted folder) falls back to the default folder, which still holds the library the move started from."""
    default_dir = Path(default_dir)
    target = read_pointer(default_dir)
    if not target:
        return default_dir, None
    if (Path(target) / LIBRARY_MARK).is_file():
        return Path(target), None
    return default_dir, target


SYSTEM_FILES = {".DS_Store", "Thumbs.db", "desktop.ini", ".localized"}


def _empty(folder):
    """No files of the person's own: system bookkeeping files (Finder, Explorer) do not count."""
    return all(child.name in SYSTEM_FILES for child in Path(folder).iterdir())


def _is_library(folder):
    return (Path(folder) / LIBRARY_MARK).is_file()


def _inside(child, parent):
    try:
        Path(child).resolve().relative_to(Path(parent).resolve())
        return True
    except ValueError:
        return False


def inspect(current, chosen):
    """What choosing `chosen` would do: {"kind": "library" | "empty" | "subfolder", "target": <folder used>}.
    Raises MoveError for a folder that cannot be used."""
    if not isinstance(chosen, str) or not chosen.strip():
        raise MoveError("invalid")
    chosen = Path(chosen.strip()).expanduser()
    if not chosen.is_absolute():
        raise MoveError("invalid")
    if not chosen.is_dir():
        raise MoveError("not_found")
    current = Path(current).resolve()
    chosen = chosen.resolve()
    if chosen == current:
        raise MoveError("same")
    if _inside(chosen, current):
        raise MoveError("inside_current")
    if _is_library(chosen):
        return {"kind": "library", "target": str(chosen)}
    if not os.access(chosen, os.W_OK):
        raise MoveError("not_writable")
    if _empty(chosen):
        return {"kind": "empty", "target": str(chosen)}
    sub = chosen / SUBFOLDER
    if sub.exists():
        if _is_library(sub):
            return {"kind": "library", "target": str(sub)}
        if sub.is_dir() and _empty(sub):
            return {"kind": "empty", "target": str(sub)}
        raise MoveError("occupied")
    return {"kind": "subfolder", "target": str(sub)}


def _folders(root):
    """Relative paths of every folder a move recreates, empty ones included."""
    return [Path(dirpath, d).relative_to(root) for dirpath, dirnames, _ in _walk(root) for d in dirnames]


def _walk(root):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_NAMES and not d.startswith(".pagetide-moving-"))
        yield dirpath, dirnames, filenames


def _files(root):
    """Relative paths of everything a move copies, sorted."""
    out = []
    for dirpath, dirnames, filenames in _walk(root):
        for name in sorted(filenames):
            if name in SKIP_NAMES or name.endswith(SKIP_SUFFIXES):
                continue
            out.append(Path(dirpath, name).relative_to(root))
    return out


def _is_sqlite(path):
    if not path.name.endswith(SQLITE_SUFFIXES):
        return False
    try:
        with path.open("rb") as handle:
            return handle.read(16) == b"SQLite format 3\x00"
    except OSError:
        return False


def _stamp(path):
    """What changes when a SQLite file is written: the file and its write-ahead log."""
    out = []
    for name in (path, Path(str(path) + "-wal")):
        try:
            stat = name.stat()
            out.append((stat.st_size, stat.st_mtime_ns))
        except OSError:
            out.append(None)
    return tuple(out)


def _check(destination):
    dst = sqlite3.connect(str(destination))
    try:
        if dst.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise MoveError("copy_failed", f"{destination.name} failed its check")
    finally:
        dst.close()


def _backup(source, destination):
    try:
        src = sqlite3.connect(f"{source.resolve().as_uri()}?mode=ro", uri=True, timeout=30)
    except sqlite3.OperationalError:
        src = None
    if src is None or not _readable(src):
        # A WAL database nobody has open (no -shm beside it, e.g. a file left by an older version) cannot be opened
        # read-only. Nothing is writing it, so its bytes and its log are a consistent copy.
        if src is not None:
            src.close()
        shutil.copy2(source, destination)
        log = Path(str(source) + "-wal")
        if log.exists():
            shutil.copy2(log, Path(str(destination) + "-wal"))
        _check(destination)
        return
    try:
        dst = sqlite3.connect(str(destination))
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()
    _check(destination)


def _readable(conn):
    try:
        conn.execute("SELECT 1 FROM sqlite_master LIMIT 1")
        return True
    except sqlite3.OperationalError:
        return False


def move(current, chosen, default_dir, progress=None):
    """Copy the library at `current` into the folder `chosen` points to (see inspect), check it, and point
    `default_dir` at it. Returns {"data_dir": <new>, "copied": <files>, "kind": ...}. The current folder is not
    changed. A failure removes the partial copy and leaves the pointer as it was."""
    current = Path(current).resolve()
    plan = inspect(str(current), chosen)
    target = Path(plan["target"])
    if plan["kind"] == "library":
        write_pointer(default_dir, target)        # a different library, not a copy: the old one is not offered for deletion
        return {"data_dir": str(target), "copied": 0, "kind": "library"}
    files = _files(current)
    total = sum((current / rel).stat().st_size for rel in files)
    # Stage inside the chosen folder (the one place known to be writable); finish with renames on the same disk.
    staging = Path(chosen).expanduser().resolve() / f".pagetide-moving-{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    try:
        for rel in _folders(current):
            (staging / rel).mkdir(parents=True, exist_ok=True)
        done = 0
        databases = [rel for rel in files if _is_sqlite(current / rel)]
        stamps = {rel: _stamp(current / rel) for rel in databases}
        for rel in files:
            source, copy = current / rel, staging / rel
            copy.parent.mkdir(parents=True, exist_ok=True)
            if rel in stamps:
                _backup(source, copy)
            else:
                shutil.copy2(source, copy)
            done += source.stat().st_size
            if progress:
                progress(done, total)
        # A database written while the rest was copying is copied again, so the new folder holds its latest state.
        for _ in range(RETRIES):
            changed = [rel for rel in databases if _stamp(current / rel) != stamps[rel]]
            if not changed:
                break
            for rel in changed:
                stamps[rel] = _stamp(current / rel)
                (staging / rel).unlink()
                _backup(current / rel, staging / rel)
        else:
            raise MoveError("busy")
        for rel in files:
            if rel not in stamps and (staging / rel).stat().st_size != (current / rel).stat().st_size:
                raise MoveError("copy_failed", f"{rel} differs after copying")
        if target.exists():          # an empty folder (inspect allowed nothing else): fill it
            for child in staging.iterdir():
                os.replace(child, target / child.name)
            staging.rmdir()
        else:                        # the PageTide subfolder of a folder that holds other things
            os.replace(staging, target)
    except MoveError:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    except Exception as exc:   # any failure (an OSError, a database that will not open...) leaves no partial copy behind
        shutil.rmtree(staging, ignore_errors=True)
        raise MoveError("copy_failed", f"{type(exc).__name__}: {exc}") from None
    write_pointer(default_dir, target, previous=current)
    return {"data_dir": str(target), "copied": len(files), "kind": plan["kind"]}

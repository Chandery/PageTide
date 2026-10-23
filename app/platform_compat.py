"""Small POSIX/Windows seams: advisory file locks, fork hooks and the default data directory.

macOS/Linux keep fcntl.flock exactly as before. Windows uses msvcrt.locking on byte 0 of the
file (a lock held through one open handle conflicts with every other handle, in-process or
not, like flock on separate open file descriptions).
"""
import os
import sys
import time
from pathlib import Path

IS_WINDOWS = os.name == "nt"

if IS_WINDOWS:
    import msvcrt
else:
    import fcntl


def _windows_try_lock(handle):
    descriptor = handle.fileno()
    os.lseek(descriptor, 0, os.SEEK_SET)
    try:
        msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
    except OSError as error:
        raise BlockingIOError(*error.args) from None


def lock_exclusive(handle, blocking=True):
    """Exclusive advisory lock on an open file. Non-blocking raises BlockingIOError when held."""
    if not IS_WINDOWS:
        fcntl.flock(handle, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        return
    while True:
        try:
            _windows_try_lock(handle)
            return
        except BlockingIOError:
            if not blocking:
                raise
            # msvcrt.LK_LOCK gives up after ~10 s; poll so a blocking lock really blocks.
            time.sleep(0.05)


def unlock(handle):
    if not IS_WINDOWS:
        fcntl.flock(handle, fcntl.LOCK_UN)
        return
    descriptor = handle.fileno()
    os.lseek(descriptor, 0, os.SEEK_SET)
    msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)


def after_fork_in_child(callback):
    """os.register_at_fork where it exists (not on Windows, which has no fork)."""
    if hasattr(os, "register_at_fork"):
        os.register_at_fork(after_in_child=callback)


def default_data_dir(environ=None, platform=None, home=None):
    """Per-user data directory: ~/Library/Application Support on macOS, %APPDATA% on Windows."""
    environ = os.environ if environ is None else environ
    platform = sys.platform if platform is None else platform
    home = Path(home) if home is not None else Path.home()
    if platform.startswith("win"):
        appdata = environ.get("APPDATA")
        base = Path(appdata) if appdata else home / "AppData" / "Roaming"
        return base / "PaperDigHelper"
    if platform == "darwin":
        return home / "Library" / "Application Support" / "PaperDigHelper"
    xdg = environ.get("XDG_DATA_HOME")
    return (Path(xdg) if xdg else home / ".local" / "share") / "PaperDigHelper"

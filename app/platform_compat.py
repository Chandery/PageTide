"""Small POSIX/Windows seams: advisory file locks, fork hooks and the default data directory.

macOS/Linux keep fcntl.flock exactly as before. Windows uses msvcrt.locking on byte 0 of the
file (a lock held through one open handle conflicts with every other handle, in-process or
not, like flock on separate open file descriptions).
"""
import errno
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
        # Only contention maps to "held"; anything else (bad descriptor...) must not turn into a poll loop.
        if error.errno not in (errno.EACCES, errno.EDEADLK, errno.EAGAIN):
            raise
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


def force_utf8_std_streams():
    """The frozen Windows exe ignores PYTHONUTF8 and uses the locale code page for pipes. Pin the std streams to
    UTF-8 (undecodable input replaced, unencodable output never raises) so both ends of every pipe agree."""
    for name, errors in (("stdin", "replace"), ("stdout", "replace"), ("stderr", "backslashreplace")):
        stream = getattr(sys, name, None)
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors=errors)


def after_fork_in_child(callback):
    """os.register_at_fork where it exists (not on Windows, which has no fork)."""
    if hasattr(os, "register_at_fork"):
        os.register_at_fork(after_in_child=callback)


def default_data_dir(environ=None, platform=None, home=None):
    """Per-user data directory: ~/Library/Application Support on macOS, %LOCALAPPDATA%\\PaperDigHelperData on Windows.

    Local (not Roaming): the library holds SQLite files and PDFs that must not roam. The folder is not
    named PaperDigHelper because the NSIS per-user installer defaults to %LOCALAPPDATA%\\PaperDigHelper
    and an uninstall must never be able to touch the library."""
    environ = os.environ if environ is None else environ
    platform = sys.platform if platform is None else platform
    home = Path(home) if home is not None else Path.home()
    if platform.startswith("win"):
        local = environ.get("LOCALAPPDATA")
        base = Path(local) if local else home / "AppData" / "Local"
        return base / "PaperDigHelperData"
    if platform == "darwin":
        return home / "Library" / "Application Support" / "PaperDigHelper"
    xdg = environ.get("XDG_DATA_HOME")
    return (Path(xdg) if xdg else home / ".local" / "share") / "PaperDigHelper"


def parent_alive_check(parent_pid, kernel32=None):
    """Return a zero-argument callable that is True while the process `parent_pid` is alive.

    POSIX: the parent of this process is still `parent_pid` (an orphan is re-parented, so os.getppid()
    changes). Windows never re-parents, so wait on a handle of the parent process instead (SYNCHRONIZE).
    `kernel32` is injectable for tests.
    """
    if not IS_WINDOWS and kernel32 is None:
        return lambda: os.getppid() == parent_pid
    if kernel32 is None:
        import ctypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.restype = ctypes.c_void_p
        kernel32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
        kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    synchronize, wait_timeout = 0x00100000, 0x102
    handle = kernel32.OpenProcess(synchronize, 0, int(parent_pid))
    if not handle:
        return lambda: False   # cannot observe the parent: treat it as gone, exactly like an orphan
    # WAIT_TIMEOUT with a zero wait means the process object is not signalled yet, i.e. still running.
    return lambda: kernel32.WaitForSingleObject(handle, 0) == wait_timeout

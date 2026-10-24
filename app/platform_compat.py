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


def add_bundled_ca_certificates():
    """Windows and macOS: point TLS at certifi's root bundle, so a packaged backend trusts the usual public roots.

    Windows: Python trusts only the roots already in the Windows store, and Windows installs many (arXiv's
    Starfield Root G2 among them) only when its own components first need one; PDF downloads failed while Edge and
    AI calls worked. ssl's load_default_certs reads the store and then SSL_CERT_FILE, so the bundle is added on top.
    macOS: the CI builds use python.org's Python, whose OpenSSL ships with no roots at all (python.org asks users to
    run "Install Certificates.command"), so every HTTPS call failed, AI included. OpenSSL does not read the
    Keychain either way. An SSL_CERT_FILE the person set, another system or a build without certifi changes
    nothing. Returns the bundle path that was set, or None."""
    if not (IS_WINDOWS or sys.platform == "darwin") or os.environ.get("SSL_CERT_FILE"):
        return None
    try:
        import certifi
    except ImportError:
        return None
    path = certifi.where()
    if not os.path.isfile(path):
        return None
    os.environ["SSL_CERT_FILE"] = path   # inherited by the organization worker processes too
    return path

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
    """Per-user data directory: ~/Library/Application Support/PageTide on macOS, %LOCALAPPDATA%\\PageTideData on Windows.

    Local (not Roaming): the library holds SQLite files and PDFs that must not roam. The folder is not
    named PageTide because the NSIS per-user installer defaults to %LOCALAPPDATA%\\PageTide
    and an uninstall must never be able to touch the library."""
    environ = os.environ if environ is None else environ
    platform = sys.platform if platform is None else platform
    home = Path(home) if home is not None else Path.home()
    if platform.startswith("win"):
        local = environ.get("LOCALAPPDATA")
        base = Path(local) if local else home / "AppData" / "Local"
        return base / "PageTideData"
    if platform == "darwin":
        return home / "Library" / "Application Support" / "PageTide"
    xdg = environ.get("XDG_DATA_HOME")
    return (Path(xdg) if xdg else home / ".local" / "share") / "PageTide"


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

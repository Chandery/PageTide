"""Local macOS/Linux cross-process claims and serial sections; no network."""
from contextlib import contextmanager
import fcntl
import hashlib
import os
from pathlib import Path
import threading
import weakref


class _SerialState:
    def __init__(self):
        self.thread_lock = threading.RLock()
        self.depth = 0
        self.handle = None


_SERIAL_STATES = weakref.WeakValueDictionary()
_SERIAL_REGISTRY_LOCK = threading.Lock()


def _reset_serial_locks_after_fork():
    global _SERIAL_STATES, _SERIAL_REGISTRY_LOCK
    # Drop only the child's inherited descriptors, without unlocking the
    # parent's shared open-file description. New child work takes its own lock.
    for state in list(_SERIAL_STATES.values()):
        if state.handle is not None:
            state.handle.close()
    _SERIAL_STATES = weakref.WeakValueDictionary()
    _SERIAL_REGISTRY_LOCK = threading.Lock()


os.register_at_fork(after_in_child=_reset_serial_locks_after_fork)


def _path(data_dir, scope):
    directory = Path(data_dir).resolve() / 'operation-locks'
    directory.mkdir(parents=True, exist_ok=True)
    return directory / (hashlib.sha256(scope.encode()).hexdigest() + '.lock')


@contextmanager
def serial(data_dir, scope):
    """Blocking resource lock, reentrant in one thread across nested callers.

    Independent descriptors can contend even within a process. Keep one local
    RLock/state per canonical lock path and take flock only at the outer level.
    Weak registry entries disappear when no section or waiter uses the resource.
    """
    path = _path(data_dir, scope)
    with _SERIAL_REGISTRY_LOCK:
        state = _SERIAL_STATES.get(str(path))
        if state is None:
            state = _SerialState()
            _SERIAL_STATES[str(path)] = state
    with state.thread_lock:
        if state.depth:
            state.depth += 1
            try:
                yield
            finally:
                state.depth -= 1
            return
        with path.open('a') as handle:
            state.handle = handle
            try:
                fcntl.flock(handle, fcntl.LOCK_EX)
                state.depth = 1
                try:
                    yield
                finally:
                    state.depth = 0
                    fcntl.flock(handle, fcntl.LOCK_UN)
            finally:
                state.handle = None


@contextmanager
def claim(data_dir, scope):
    with _path(data_dir, scope).open('a') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('AI 正在判断，请稍候') from None
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)

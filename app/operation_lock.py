"""Local macOS/Linux cross-process claims; no timer, model or network."""
from contextlib import contextmanager
import fcntl
import hashlib
from pathlib import Path


@contextmanager
def claim(data_dir, scope):
    directory = Path(data_dir) / 'operation-locks'
    directory.mkdir(exist_ok=True)
    path = directory / (hashlib.sha256(scope.encode()).hexdigest() + '.lock')
    with path.open('a') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('AI 正在判断，请稍候') from None
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)

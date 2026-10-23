"""Run the Python unit tests (what CI runs): `python scripts/run_tests.py [unittest discover args]`.

On Windows only, TemporaryDirectory cleanup becomes tolerant: collect garbage first (closing SQLite
connections that are only unreachable, not closed), and ignore what still cannot be deleted. Windows cannot
delete a directory holding an open file, which on POSIX is silently allowed. Test failures stay visible; only
the directory-removal step is lenient. Elsewhere this is exactly `python -m unittest discover -s tests`.
"""
import gc
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def make_cleanup_tolerant(directory_class=tempfile.TemporaryDirectory):
    original_init, original_cleanup = directory_class.__init__, directory_class.cleanup

    def init(self, *args, **kwargs):
        kwargs.setdefault("ignore_cleanup_errors", True)   # Python 3.10+
        original_init(self, *args, **kwargs)

    def cleanup(self):
        gc.collect()
        original_cleanup(self)

    directory_class.__init__, directory_class.cleanup = init, cleanup


def main(argv):
    if sys.platform == "win32":
        make_cleanup_tolerant()
    sys.path.insert(0, ROOT)
    os.chdir(ROOT)
    arguments = argv or ["-s", "tests"]
    unittest.main(module=None, argv=["unittest", "discover", *arguments])


if __name__ == "__main__":
    main(sys.argv[1:])

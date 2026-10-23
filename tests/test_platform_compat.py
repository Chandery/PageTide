"""Cross-platform seams: file locks (real POSIX branch, simulated Windows branch) and the data directory."""
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from app import operation_lock, platform_compat as pc


@unittest.skipIf(sys.platform == "win32", "real fcntl branch; the Windows branch is exercised by the simulated tests below and by CI")
class PosixLockTests(unittest.TestCase):
    def test_exclusive_nonblocking_lock_conflicts_across_handles_and_releases(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.lock"
            with path.open("a") as one, path.open("a") as two:
                pc.lock_exclusive(one, blocking=False)
                with self.assertRaises(BlockingIOError):
                    pc.lock_exclusive(two, blocking=False)
                pc.unlock(one)
                pc.lock_exclusive(two, blocking=False)
                pc.unlock(two)

    def test_claim_and_serial_use_the_helper_with_the_old_semantics(self):
        with tempfile.TemporaryDirectory() as tmp:
            with operation_lock.claim(tmp, "scope"):
                with self.assertRaisesRegex(ValueError, "AI 正在判断"):
                    with operation_lock.claim(tmp, "scope"):
                        pass
            with operation_lock.claim(tmp, "scope"):
                pass
            with operation_lock.serial(tmp, "s"):
                with operation_lock.serial(tmp, "s"):
                    pass


class FakeMsvcrt:
    LK_NBLCK, LK_UNLCK = 2, 0

    def __init__(self):
        self.held, self.calls = set(), []

    def locking(self, descriptor, mode, nbytes):
        self.calls.append((mode, nbytes, os.lseek(descriptor, 0, os.SEEK_CUR)))
        if mode == self.LK_NBLCK:
            if self.held:
                raise OSError(13, "Permission denied")
            self.held.add(descriptor)
        else:
            self.held.discard(descriptor)


class WindowsBranchTests(unittest.TestCase):
    def patched(self, fake):
        stack = mock.patch.object(pc, "IS_WINDOWS", True)
        stack2 = mock.patch.object(pc, "msvcrt", fake, create=True)
        return stack, stack2

    def test_nonblocking_lock_locks_byte_zero_and_maps_failure_to_blockingioerror(self):
        fake = FakeMsvcrt()
        a, b = self.patched(fake)
        with a, b, tempfile.TemporaryFile("a+") as one, tempfile.TemporaryFile("a+") as two:
            one.write("pad")
            pc.lock_exclusive(one, blocking=False)
            self.assertEqual(fake.calls[-1], (FakeMsvcrt.LK_NBLCK, 1, 0))
            with self.assertRaises(BlockingIOError):
                pc.lock_exclusive(two, blocking=False)
            pc.unlock(one)
            self.assertEqual(fake.calls[-1][0], FakeMsvcrt.LK_UNLCK)
            pc.lock_exclusive(two, blocking=False)

    def test_blocking_lock_polls_until_released(self):
        fake = FakeMsvcrt()
        fake.held.add(-1)
        a, b = self.patched(fake)
        sleeps = []

        def sleep(seconds):
            sleeps.append(seconds)
            fake.held.clear()

        with a, b, mock.patch.object(pc.time, "sleep", sleep), tempfile.TemporaryFile("a+") as handle:
            pc.lock_exclusive(handle)
        self.assertEqual(len(sleeps), 1)


class DataDirTests(unittest.TestCase):
    def test_macos_unchanged(self):
        self.assertEqual(pc.default_data_dir({}, "darwin", "/Users/u"), Path("/Users/u/Library/Application Support/PaperDigHelper"))

    def test_windows_uses_appdata_then_roaming_fallback(self):
        self.assertEqual(pc.default_data_dir({"APPDATA": "C:/Users/u/AppData/Roaming"}, "win32", "C:/Users/u"),
                         Path("C:/Users/u/AppData/Roaming/PaperDigHelper"))
        self.assertEqual(pc.default_data_dir({}, "win32", "C:/Users/u"), Path("C:/Users/u/AppData/Roaming/PaperDigHelper"))

    def test_other_posix_uses_xdg(self):
        self.assertEqual(pc.default_data_dir({"XDG_DATA_HOME": "/x"}, "linux", "/h"), Path("/x/PaperDigHelper"))
        self.assertEqual(pc.default_data_dir({}, "linux", "/h"), Path("/h/.local/share/PaperDigHelper"))

    def test_fork_hook_is_optional(self):
        with mock.patch.object(pc.os, "register_at_fork", create=True) as hook:
            pc.after_fork_in_child(print)
            hook.assert_called_once_with(after_in_child=print)
        saved = getattr(os, "register_at_fork", None)
        try:
            if saved:
                del os.register_at_fork
            pc.after_fork_in_child(print)  # must not raise
        finally:
            if saved:
                os.register_at_fork = saved


if __name__ == "__main__":
    unittest.main()

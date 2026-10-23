"""Cross-platform seams: file locks (real POSIX branch, simulated Windows branch) and the data directory."""
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from app import operation_lock, platform_compat as pc


class RealLockTests(unittest.TestCase):
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

    def test_unexpected_errors_are_not_reported_as_contention(self):
        class Broken:
            LK_NBLCK, LK_UNLCK = 2, 0

            def locking(self, descriptor, mode, nbytes):
                raise OSError(9, "bad file descriptor")

        a, b = self.patched(Broken())
        with a, b, tempfile.TemporaryFile("a+") as handle:
            with self.assertRaises(OSError) as raised:
                pc.lock_exclusive(handle)   # blocking: must raise, not poll forever
            self.assertNotIsInstance(raised.exception, BlockingIOError)

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


class ParentWatchTests(unittest.TestCase):
    def test_posix_branch_compares_the_current_parent(self):
        with mock.patch.object(pc, "IS_WINDOWS", False):
            self.assertTrue(pc.parent_alive_check(os.getppid())())
            self.assertFalse(pc.parent_alive_check(os.getppid() + 100000)())

    def test_windows_branch_waits_on_a_process_handle(self):
        class Kernel:
            def __init__(self, handle, state):
                self.handle, self.state, self.opened = handle, state, []

            def OpenProcess(self, access, inherit, pid):
                self.opened.append((access, inherit, pid))
                return self.handle

            def WaitForSingleObject(self, handle, milliseconds):
                assert handle == self.handle and milliseconds == 0
                return self.state[0]

        state = [0x102]   # WAIT_TIMEOUT: still running
        kernel = Kernel(7, state)
        with mock.patch.object(pc, "IS_WINDOWS", True):
            alive = pc.parent_alive_check(4321, kernel)
            self.assertEqual(kernel.opened, [(0x00100000, 0, 4321)])   # SYNCHRONIZE only
            self.assertTrue(alive())
            state[0] = 0   # WAIT_OBJECT_0: the parent exited
            self.assertFalse(alive())
            self.assertFalse(pc.parent_alive_check(4321, Kernel(0, state))())   # cannot open: treated as gone


class DesktopLogTests(unittest.TestCase):
    def test_stderr_log_is_created_and_size_capped_with_one_rotated_copy(self):
        from app import desktop
        saved = sys.stderr
        with tempfile.TemporaryDirectory() as tmp:
            try:
                path = desktop.redirect_stderr_to_log(tmp, limit=3)
                print("first", file=sys.stderr)
                sys.stderr.close()
                path = desktop.redirect_stderr_to_log(tmp, limit=3)   # bigger than the cap: rotate
                print("second", file=sys.stderr)
                sys.stderr.close()
            finally:
                sys.stderr = saved
            self.assertEqual(path.read_text(encoding="utf-8"), "second\n")
            self.assertEqual((path.parent / "backend.log.1").read_text(encoding="utf-8"), "first\n")


class TolerantCleanupTests(unittest.TestCase):
    def test_runner_makes_directory_cleanup_tolerant_after_a_gc(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("run_tests", Path(__file__).resolve().parents[1] / "scripts" / "run_tests.py")
        runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runner)

        class Directory(tempfile.TemporaryDirectory):
            pass

        runner.make_cleanup_tolerant(Directory)
        with mock.patch.object(runner.gc, "collect") as collected:
            directory = Directory()
            self.assertTrue(directory._ignore_cleanup_errors)
            directory.cleanup()
            collected.assert_called()   # the tempfile module may also collect on cleanup; at least our call
        # (No assertion about the stock class: on Windows the CI runner has already made it tolerant.)


class SmokeDiagnosticsTests(unittest.TestCase):
    def test_report_prints_exit_status_and_the_tail_of_stderr_and_the_backend_log(self):
        import importlib.util
        import io
        from contextlib import redirect_stderr
        spec = importlib.util.spec_from_file_location("vpr", Path(__file__).resolve().parents[1] / "scripts" / "verify_packaged_route.py")
        vpr = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(vpr)

        class Process:
            def poll(self):
                return 3

        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryFile("w+") as errors:
            errors.write("\n".join("line%d" % n for n in range(500)))
            (Path(tmp) / "logs").mkdir()
            (Path(tmp) / "logs" / "backend.log").write_text("from the log\n", encoding="utf-8")
            out = io.StringIO()
            with redirect_stderr(out):
                vpr.report_backend(Process(), errors, tmp, lines=5)
        text = out.getvalue()
        self.assertIn("exit status (None = still running): 3", text)
        self.assertIn("line499", text)
        self.assertNotIn("line100\n", text)
        self.assertIn("from the log", text)


class BuildPythonTests(unittest.TestCase):
    def load(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("build_desktop", Path(__file__).resolve().parents[1] / "scripts" / "build_desktop.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_env_var_wins_and_macos_without_the_venv_fails_instead_of_falling_back(self):
        build = self.load()
        with mock.patch.dict(os.environ, {"PDH_BUILD_PYTHON": "/x/python"}):
            self.assertEqual(build.build_python(), "/x/python")
        env = {k: v for k, v in os.environ.items() if k != "PDH_BUILD_PYTHON"}
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, env, clear=True):
            build.ROOT = Path(tmp)
            with mock.patch.object(build.sys, "platform", "darwin"):
                with self.assertRaises(SystemExit):
                    build.build_python()
            with mock.patch.object(build.sys, "platform", "win32"):
                self.assertEqual(build.build_python(), sys.executable)


    def test_utf8_python_option_only_on_windows(self):
        build = self.load()
        with mock.patch.object(build.sys, "platform", "win32"):
            self.assertEqual(build.python_options(), ["--python-option", "X utf8"])
        with mock.patch.object(build.sys, "platform", "darwin"):
            self.assertEqual(build.python_options(), [])


class AppCloseTests(unittest.TestCase):
    def test_close_releases_the_database_and_is_idempotent(self):
        from app.service import App
        with tempfile.TemporaryDirectory() as tmp:
            app = App(root=Path(__file__).resolve().parents[1], data_dir=Path(tmp) / "data")
            app.close()
            app.close()
            with self.assertRaises(Exception):
                app.store.conn.execute("select 1")


class DataDirTests(unittest.TestCase):
    def test_macos_unchanged(self):
        self.assertEqual(pc.default_data_dir({}, "darwin", "/Users/u"), Path("/Users/u/Library/Application Support/PaperDigHelper"))

    def test_windows_uses_local_appdata_and_never_the_installer_directory(self):
        self.assertEqual(pc.default_data_dir({"LOCALAPPDATA": "C:/Users/u/AppData/Local", "APPDATA": "C:/Users/u/AppData/Roaming"},
                                             "win32", "C:/Users/u"), Path("C:/Users/u/AppData/Local/PaperDigHelperData"))
        self.assertEqual(pc.default_data_dir({}, "win32", "C:/Users/u"), Path("C:/Users/u/AppData/Local/PaperDigHelperData"))
        # NSIS currentUser installs into %LOCALAPPDATA%\PaperDigHelper; the library must be a different folder.
        self.assertNotEqual(pc.default_data_dir({"LOCALAPPDATA": "C:/L"}, "win32", "C:/u").name, "PaperDigHelper")

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

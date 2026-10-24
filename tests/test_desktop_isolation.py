"""Exercise the real desktop backend with disposable libraries and no provider key."""
import http.cookiejar
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import tempfile
import unittest
import urllib.error
import urllib.request

from app.db import Store


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipIf(sys.platform == "win32", "uses select.select on pipes, HOME and the macOS Library path; the Windows data-dir choice is covered by tests/test_platform_compat.py")
class DesktopIsolationTests(unittest.TestCase):
    def _seed(self, directory, key):
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "AI_DISABLED").touch()
        store = Store(directory / "pagetide.sqlite")
        store.init()
        store.conn.execute("INSERT INTO projects(id,name,creation_mode,creation_timestamp,keywords) VALUES ('p','P','manual','2026-01-01','[]')")
        store.conn.commit()
        store.upsert_papers([{"key": key, "title": key,
                              "abstract": "Disposable offline test paper.",
                              "published": "2026-01-01", "group_name": "field"}])
        store.conn.close()

    def _run_backend(self, home, directory=None, expected_key="isolated-library"):
        env = dict(os.environ, HOME=str(home), DEEPSEEK_API_KEY="", PAGETIDE_DEV="0")
        env.pop("PAGETIDE_DATA", None)
        if directory is not None:
            env["PAGETIDE_DATA"] = str(directory)
        with tempfile.TemporaryFile(mode="w+") as errors:
            code = ("import socket; "
                    "socket.socket.connect = lambda *args, **kwargs: "
                    "(_ for _ in ()).throw(RuntimeError('Test prohibits outbound network')); "
                    "from app.desktop import main; main()")
            process = subprocess.Popen([sys.executable, "-c", code], cwd=ROOT,
                                       env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                       stderr=errors, text=True)
            try:
                ready = select.select([process.stdout], [], [], 20)[0]
                if not ready:
                    errors.seek(0)
                    self.fail("Desktop backend did not announce readiness: " + errors.read()[-2000:])
                line = process.stdout.readline()
                if not line.startswith("PAGETIDE_READY "):
                    errors.seek(0)
                    self.fail("Desktop startup failed, exit=" + str(process.poll()) + ": " + errors.read()[-2000:])
                url = line.strip().split(" ", 1)[1]
                base = url.split("/_desktop/", 1)[0]
                with self.assertRaises(urllib.error.HTTPError) as denied:
                    urllib.request.urlopen(base + "/api/state", timeout=10)
                self.assertEqual(denied.exception.code, 403)
                denied.exception.close()
                opener = urllib.request.build_opener(
                    urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
                with opener.open(url, timeout=10) as response:
                    self.assertEqual(response.status, 200)
                with opener.open(base + "/api/paper?key=" + expected_key, timeout=10) as response:
                    self.assertEqual(json.load(response)["key"], expected_key)
                process.stdin.close()
                self.assertEqual(process.wait(timeout=15), 0)
                errors.seek(0)
                stderr = errors.read()
                self.assertNotIn("PAGETIDE_BOOTSTRAP_FAILED", stderr)
                self.assertNotIn("Test prohibits outbound network", stderr)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=5)
                process.stdout.close()
                if not process.stdin.closed:
                    process.stdin.close()

    def test_explicit_library_is_used_by_bootstrap_and_requests(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "fake-home"
            default = home / "Library" / "Application Support" / "PageTide"
            directory = Path(tmp) / "isolated-library"
            # Also seed the fallback: the regression never contacts discovery services.
            self._seed(default, "fallback-library")
            self._seed(directory, "isolated-library")
            before = {p.relative_to(default): p.read_bytes() for p in default.rglob("*") if p.is_file()}
            self._run_backend(home, directory)
            self._run_backend(home, directory)
            after = {p.relative_to(default): p.read_bytes() for p in default.rglob("*") if p.is_file()}
            self.assertEqual(before, after, "Explicit isolation changed the default library")
            self.assertTrue((directory / ".desktop.lock").is_file())
            self.assertTrue((directory / "app" / "budget.json").is_file())

    def test_default_library_remains_supported(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            directory = home / "Library" / "Application Support" / "PageTide"
            self._seed(directory, "isolated-library")
            self._run_backend(home)
            self.assertTrue((directory / ".desktop.lock").is_file())

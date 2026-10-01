import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from app import server


class WorkerStdoutPurityTests(unittest.TestCase):
    """The worker's stdout is a single JSON blob; server.organization_job json.loads it whole.

    Regression: apply_migrations() used to print its progress to stdout, so a
    first run on a fresh database produced "Database is up to date (version 1)"
    ahead of the JSON and the knowledge graph failed to load with
    "JSONDecodeError: Expecting value: line 1 column 1 (char 0)".
    """

    def _run_worker(self, db_path):
        # Same argv shape the server builds: db, project, parent pid, operation.
        return subprocess.run(
            [sys.executable, "-m", "app.organization_worker",
             db_path, "default", str(os.getpid()), "graph"],
            capture_output=True, text=True, timeout=120,
        )

    def test_fresh_database_stdout_is_pure_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "fresh.sqlite")
            result = self._run_worker(db)
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)  # must not raise
            self.assertIn("relations", payload)
            self.assertEqual(result.stdout.strip().count("\n"), 0,
                             f"stdout carried more than one value: {result.stdout!r}")

    def test_second_run_stdout_is_pure_json(self):
        """The up-to-date branch is the one that used to pollute stdout."""
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "twice.sqlite")
            self._run_worker(db)
            result = self._run_worker(db)
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertIn("relations", payload)

    def test_migration_progress_goes_to_stderr_not_stdout(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self._run_worker(os.path.join(tmp, "logged.sqlite"))
            self.assertIn("migration", result.stderr.lower(),
                          "expected migration diagnostics on stderr")
            self.assertNotIn("migration", result.stdout.lower())
            self.assertNotIn("Database is up to date", result.stdout)


class WorkerStdinTests(unittest.TestCase):
    """Profile terms are user text: the worker takes them on stdin, never in argv."""

    def _run(self, db, payload, operation="suggest"):
        return subprocess.run(
            [sys.executable, "-m", "app.organization_worker", db, "default", str(os.getpid()),
             operation, "stdin"], input=payload, capture_output=True, text=True, timeout=120)

    def test_profile_reaches_suggest(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self._run(os.path.join(tmp, "s.sqlite"),
                               json.dumps({"profile": {"pinned": ["world models"], "project": "WM"}}))
            self.assertEqual(result.returncode, 0, result.stderr)
            profile = json.loads(result.stdout)["suggestions"]["profile"]
            self.assertEqual(profile["pinned"], ["world models"])
            self.assertEqual(profile["project"], "WM")

    def test_rejects_other_keys_operations_and_bad_profiles(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "r.sqlite")
            for payload, operation in ((json.dumps({"action": "undo"}), "suggest"),
                                       (json.dumps([]), "suggest"),
                                       (json.dumps({"profile": {"pinned": "x"}}), "suggest"),
                                       (json.dumps({"profile": {}}), "graph")):
                result = self._run(db, payload, operation)
                self.assertNotEqual(result.returncode, 0, payload)
                self.assertEqual(result.stdout, "")

    def test_job_sends_body_on_stdin_not_argv(self):
        from unittest.mock import MagicMock
        worker = MagicMock()
        worker.communicate.return_value = ("{}", "")
        worker.returncode = 0
        worker.poll.return_value = 0
        with patch.object(server.subprocess, "Popen", return_value=worker) as popen:
            server.organization_job("db", "default", "suggest", {"profile": {"pinned": ["秘密词"]}})
        argv = popen.call_args.args[0]
        self.assertEqual(argv[-1], "stdin")
        self.assertNotIn("秘密词", " ".join(argv))
        sent = worker.communicate.call_args.kwargs["input"]
        self.assertTrue(sent.isascii())  # escaped JSON: no locale-dependent pipe encoding
        self.assertEqual(json.loads(sent)["profile"]["pinned"], ["秘密词"])


class SuggestionProfileTests(unittest.TestCase):
    def test_interest_terms_are_bounded_like_pinned_terms(self):
        from app.organization_facets import suggest_groups
        terms = [{"term": "x" * 101}, {"term": ""}, {"term": None}] + [{"term": "t%d" % i} for i in range(60)]
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "harness").mkdir()
            (Path(tmp) / "harness" / "seeds.json").write_text(json.dumps({"seeds": []}))
            (Path(tmp) / "harness" / "budget.json").write_text(
                (Path(__file__).resolve().parents[1] / "harness" / "budget.json").read_text())
            with patch.dict(os.environ, {"PAPERDIGHELPER_DATA": tmp}):
                app = server.make_app(tmp)
            try:
                with patch("app.profile_insights.keywords", return_value=terms):
                    profile = server.suggestion_profile(app)
            finally:
                app.store.close()
        self.assertEqual(profile["interest"], ["t%d" % i for i in range(40)])
        suggest_groups([], profile)  # the worker would accept it


class WorkerLifecycleTests(unittest.TestCase):
    def tearDown(self):
        server.stop_organization_workers()
        server.ORGANIZATION_STOPPING.clear()

    def test_shutdown_terminates_and_reaps_only_registered_worker(self):
        worker = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        with server.ORGANIZATION_PROCESSES_LOCK:
            server.ORGANIZATION_PROCESSES.add(worker)
        try:
            server.stop_organization_workers()
            self.assertIsNotNone(worker.poll())
            with self.assertRaisesRegex(ValueError, "退出"):
                server.organization_job("unused", "default")
        finally:
            with server.ORGANIZATION_PROCESSES_LOCK:
                server.ORGANIZATION_PROCESSES.discard(worker)

    def test_timeout_kills_and_reaps_worker_and_releases_lock(self):
        from unittest.mock import MagicMock
        worker = MagicMock()
        worker.communicate.side_effect = [subprocess.TimeoutExpired("worker", 120), ("", "")]
        worker.poll.return_value = None
        with patch.object(server.subprocess, "Popen", return_value=worker):
            with self.assertRaises(subprocess.TimeoutExpired):
                server.organization_job("unused", "default")
        worker.kill.assert_called_once()
        self.assertEqual(worker.communicate.call_count, 2)
        self.assertNotIn(worker, server.ORGANIZATION_PROCESSES)
        self.assertFalse(server.ORGANIZATION_JOB_LOCK.locked())

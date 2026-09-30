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

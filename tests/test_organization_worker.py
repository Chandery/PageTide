import subprocess
import sys
import unittest
from unittest.mock import patch

from app import server


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

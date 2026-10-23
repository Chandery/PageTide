import json
import http.client
import threading
import time
import unittest

from tests import test_app_server
from app import server


class OrganizationHTTPTests(unittest.TestCase):
    def setUp(self):
        test_app_server.ServerSmokeTests.setUp(self)
        # Create and migrate the database before the first request. On a slow Windows runner the first
        # request otherwise spends its whole 10 s client timeout creating a fresh database.
        server.make_app(str(self.root)).close()

    def request_org(self, body=None, origin=None, host=None):
        headers = {"Content-Type": "application/json"}
        if origin:
            headers["Origin"] = origin
        if host:
            headers["Host"] = host
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            connection.request("GET" if body is None else "POST", "/api/organization",
                               body=None if body is None else json.dumps(body).encode(), headers=headers)
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def seed(self):
        app = server.make_app(str(self.root))
        try:
            app.store.upsert_papers([{"key": "org-paper", "title": "World model planning",
                                     "abstract": "latent dynamics planning", "group_name": "field"}])
            app.store.save_to_library("org-paper", "original note")
        finally:
            app.store.close()

    def test_organization_round_trip(self):
        self.seed()
        status, snapshot = self.request_org()
        self.assertEqual(status, 200)
        self.assertEqual(snapshot["items"][0]["note"], "original note")
        status, snapshot = self.request_org({"action": "direction-save", "name": "Planning",
                                             "color": "#167b70"})
        self.assertEqual(status, 200)
        direction = snapshot["directions"][0]["id"]
        status, snapshot = self.request_org({"action": "membership", "keys": ["org-paper"],
                                             "add": [direction]})
        self.assertEqual(snapshot["items"][0]["directions"], [direction])
        status, snapshot = self.request_org({"action": "note", "key": "org-paper",
                                             "version": 0, "text": "# My note"})
        self.assertEqual(status, 200)
        self.assertEqual(self.request_org()[1]["items"][0]["note"], "# My note")
        self.assertEqual(self.request_org({"action": "note", "key": "org-paper",
                                           "version": 0, "text": "stale"})[0], 400)
        status, history = self.request_org({"action": "history", "key": "org-paper"})
        self.assertGreaterEqual(len(history["history"]), 2)

    def test_organization_rejects_invalid_and_foreign_requests(self):
        self.assertEqual(self.request_org([])[0], 400)
        self.assertEqual(self.request_org({"action": "unknown"})[0], 400)
        self.assertEqual(self.request_org({"action": "undo"}, "https://attacker.invalid")[0], 403)
        self.assertEqual(self.request_org(host="attacker.invalid")[0], 403)

    def test_classification_worker_returns_job_result(self):
        self.seed()
        status, payload = self.request_org({"action": "suggest"})
        self.assertEqual(status, 200)
        job_id = payload["job"]["id"]
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            job = server._job_get(job_id)
            if job["state"] != "running":
                break
            threading.Event().wait(0.05)
        self.assertEqual(job["state"], "done", job.get("error"))
        self.assertIn("suggestions", job["result"])

    def test_suggestions_follow_the_project_profile_sent_over_stdin(self):
        self.seed()
        app = server.make_app(str(self.root))
        try:
            app.pin_terms(["world model", "planning"])
            project = app.get_default_project_id()
        finally:
            app.store.close()
        status, payload = self.request_org({"action": "suggest", "project_id": project})
        self.assertEqual(status, 200)
        job_id = payload["job"]["id"]
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            job = server._job_get(job_id)
            if job["state"] != "running":
                break
            threading.Event().wait(0.05)
        self.assertEqual(job["state"], "done", job.get("error"))
        profile = job["result"]["suggestions"]["profile"]
        self.assertEqual(profile["pinned"], ["world model", "planning"])
        self.assertEqual(self.request_org({"action": "suggest", "project_id": "no-such-project"})[0], 400)

    def test_operation_alias_cannot_bypass_worker(self):
        from unittest.mock import patch
        with patch.object(server, "_job_start", return_value={"id": "bounded", "state": "done"}) as job:
            status, payload = self.request_org({"op": "suggest"})
            self.assertEqual(status, 200)
            self.assertEqual(payload["job"]["id"], "bounded")
            job.assert_called_once()
        self.assertEqual(self.request_org({"op": "suggest", "action": "undo"})[0], 400)

    def test_graph_uses_bounded_job_and_does_not_create_suggestions(self):
        self.seed()
        before = self.request_org()[1]
        status, payload = self.request_org({"action": "graph"})
        self.assertEqual(status, 200)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            job = server._job_get(payload["job"]["id"])
            if job["state"] != "running":
                break
            threading.Event().wait(0.05)
        self.assertEqual(job["state"], "done", job.get("error"))
        self.assertIn("relations", job["result"])
        self.assertEqual(self.request_org()[1], before)

    def test_shared_job_and_home_routes_reject_rebound_host(self):
        for path in ("/api/home", "/api/jobs/job-1"):
            connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
            try:
                connection.request("GET", path, headers={"Host": "attacker.invalid"})
                response = connection.getresponse()
                self.assertEqual(response.status, 403)
                response.read()
            finally:
                connection.close()

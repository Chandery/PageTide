import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import server


class ServerSmokeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "harness").mkdir()
        (self.root / "harness" / "seeds.json").write_text(json.dumps({"seeds": []}))
        (self.root / "harness" / "budget.json").write_text(
            (Path(__file__).resolve().parents[1] / "harness" / "budget.json").read_text())
        self.httpd = server.build_server(port=0, root=str(self.root))
        self.port = self.httpd.server_address[1]
        thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(self.httpd.server_close)
        self.addCleanup(self.httpd.shutdown)

    def _get(self, path):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=5) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()

    def _post(self, path, payload):
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}", data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def _delete(self, path, payload):
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}", data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"}, method="DELETE")
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def test_index_and_state_are_served(self):
        status, body = self._get("/")
        self.assertEqual(status, 200)
        self.assertIn(b"PaperDigHelper", body)
        status, body = self._get("/api/state")
        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertIn("profile", payload)
        self.assertIsInstance(payload["cards"], list)
        status, body = self._get("/api/home")
        payload = json.loads(body)
        self.assertIn("stats", payload)
        self.assertIn("summaries", payload)

    def test_paper_detail_endpoint(self):
        app = server.make_app(str(self.root))
        # A realistic key contains '://' and '/', which is why the API takes ?key= or a POST body.
        url_key = "https://doi.org/10.48550/arxiv.2609.00001"
        app.store.upsert_papers([{"key": url_key, "title": "World Model Detail",
                                  "abstract": "full abstract text", "published": "2026-08-01",
                                  "group_name": "field"}])
        from urllib.parse import quote
        status, body = self._get(f"/api/paper?key={quote(url_key, safe='')}")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["abstract"], "full abstract text")
        status, body = self._get(f"/api/paper/{quote(url_key, safe='')}")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["key"], url_key)
        status, _ = self._get("/api/paper?key=missing")
        self.assertEqual(status, 404)

    def test_project_guidance_and_explicit_paper_sharing_routes(self):
        status, created = self._post("/api/projects", {"name": "项目 A", "creation_mode": "manual", "keywords": ["world models"]})
        self.assertEqual(status, 200)
        project_id = created["project_id"]
        status, bad = self._post("/api/projects", {"name": "坏项目", "creation_mode": "unknown"})
        self.assertEqual(status, 400)
        self.assertIn("invalid", bad["error"])
        status, session = self._post("/api/project-guidance/sessions", {"name": "引导项目", "goal": "理解 JEPA"})
        self.assertEqual(status, 201)
        sid = session["session"]["id"]
        status, resumed_raw = self._get(f"/api/project-guidance/sessions/{sid}")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(resumed_raw)["session"]["id"], sid)
        status, turn = self._post(f"/api/project-guidance/sessions/{sid}/turn", {"message": "关注规划", "dry_run": True})
        self.assertEqual(status, 200)
        self.assertEqual(turn["mode"], "local")
        status, cancelled = self._delete(f"/api/project-guidance/sessions/{sid}", {})
        self.assertEqual(status, 200)
        self.assertTrue(cancelled["cancelled"])
        status, _ = self._delete(f"/api/project-guidance/sessions/{sid}", {})
        self.assertEqual(status, 409)
        status, _ = self._delete("/api/project-guidance/sessions/missing", {})
        self.assertEqual(status, 404)

        app = server.make_app(str(self.root))
        app.store.upsert_papers([{"key": "shared", "title": "Shared", "abstract": "x", "published": "2026-01-01",
                                  "group_name": "field", "project_id": project_id}])
        status, relation = self._post("/api/project-papers", {"project_id": project_id, "paper_key": "shared"})
        self.assertEqual(status, 200)
        self.assertTrue(relation["added"])
        status, projects_raw = self._get("/api/paper/shared/projects")
        self.assertEqual(status, 200)
        projects = json.loads(projects_raw)
        self.assertEqual(projects["projects"][0]["project_id"], project_id)
        status, removed = self._delete("/api/project-papers", {"project_id": project_id, "paper_key": "shared"})
        self.assertEqual(status, 200)
        self.assertTrue(removed["removed"])

    def _upload(self, data, name="paper.pdf"):
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/seeds/pdf", data=data,
            headers={"Content-Type": "application/pdf", "X-Filename": urllib.parse.quote(name)}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def test_seed_routes_validate_input_without_the_network(self):
        status, out = self._post("/api/seeds/resolve", {"input": "attention is all you need"})
        self.assertEqual((status, out["status"]), (200, "invalid_input"))  # free text is searched, never sent as an id
        self.assertEqual(self._post("/api/seeds/resolve", {"input": "  "})[0], 400)
        self.assertEqual(self._post("/api/seeds/search", {"query": "ab"})[0], 400)

    def test_dropped_pdf_is_kept_and_attached_to_the_resolved_seed(self):
        from app import creation
        creation._SEED_CACHE.clear()
        pdf = b"%PDF-1.7\n1 0 obj<<>>endobj\n%%EOF\n"
        self.assertEqual(self._upload(b"<html>nope</html>")[0], 400)
        status, uploaded = self._upload(pdf, "my paper.pdf")
        self.assertEqual(status, 200)
        self.assertEqual(uploaded["filename"], "my paper.pdf")
        work = {"id": "https://openalex.org/W77", "doi": "https://doi.org/10.48550/arxiv.2401.00001", "ids": {},
                "title": "Latent World Models", "publication_date": "2024-01-02", "authorships": []}
        with mock.patch("app.sources.OpenAlex.work", return_value=work):
            status, found = self._post("/api/seeds/resolve", {"input": "arXiv:2401.00001"})
            self.assertEqual((status, found["status"]), (200, "resolved"))
            status, created = self._post("/api/projects", {
                "name": "PDF 项目", "creation_mode": "manual", "keywords": ["world models"],
                "seeds": [{"identifier": found["paper"]["openalex_id"], "pdf_id": uploaded["pdf_id"]}]})
        self.assertEqual(status, 200)
        outcome = created["seed_results"][0]
        self.assertEqual((outcome["status"], outcome["pdf_attached"]), ("resolved", True))
        status, body = self._get(f"/api/pdf/view?key={urllib.parse.quote(outcome['key'], safe='')}")
        self.assertEqual((status, body), (200, pdf))

    def test_guidance_search_and_retry_routes(self):
        status, session = self._post("/api/project-guidance/sessions", {"name": "检索", "goal": "world models"})
        sid = session["session"]["id"]
        self.assertEqual(self._post(f"/api/project-guidance/sessions/{sid}/search", {"query": ""})[0], 400)
        status, out = self._post(f"/api/project-guidance/sessions/{sid}/turn", {"retry": True})
        self.assertEqual(status, 400)  # nothing to retry yet
        status, out = self._post(f"/api/project-guidance/sessions/{sid}/turn",
                                 {"message": "关注规划", "dry_run": True, "draft": {"keywords": ["jepa"]}})
        self.assertEqual((status, out["reason_code"]), (200, "dry_run"))
        self.assertIn("jepa", out["session"]["draft"]["keywords"])  # edits made on the page reach the draft
        status, out = self._post(f"/api/project-guidance/sessions/{sid}/turn", {"retry": True, "dry_run": True})
        self.assertEqual(status, 200)

    def test_profile_freeze_and_restore_routes(self):
        status, created = self._post("/api/projects", {"name": "画像", "creation_mode": "manual",
                                                       "keywords": ["world models"]})
        project_id = created["project_id"]
        status, frozen = self._post("/api/profile/freeze", {"project_id": project_id, "frozen": True})
        self.assertEqual(status, 200)
        self.assertTrue(frozen["profile"]["frozen"])
        status, _ = self._post("/api/profile/freeze", {"project_id": project_id, "frozen": "yes"})
        self.assertEqual(status, 400)
        status, restored = self._post("/api/profile/restore", {"project_id": project_id})
        self.assertEqual(status, 200)
        self.assertFalse(restored["profile"]["frozen"])
        self.assertEqual(restored["profile"]["pinned_terms"], ["world models"])
        status, _ = self._post("/api/profile/restore", {"project_id": "missing"})
        self.assertEqual(status, 400)

    def test_paper_detail_via_post_body(self):
        """This is the path the UI uses; a POST body avoids URL-encoding issues."""
        app = server.make_app(str(self.root))
        url_key = "https://doi.org/10.48550/arxiv.2610.00002"
        app.store.upsert_papers([{"key": url_key, "title": "Posted Detail",
                                  "abstract": "via body", "published": "2026-08-02",
                                  "group_name": "field"}])
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/detail",
            data=json.dumps({"key": url_key}).encode(), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = json.loads(response.read())
        self.assertEqual(payload["key"], url_key)
        self.assertEqual(payload["abstract"], "via body")

    def test_home_reports_server_version(self):
        status, body = self._get("/api/home")
        self.assertEqual(status, 200)
        self.assertIn("server_version", json.loads(body))

    def test_invalid_project_id_is_a_client_error(self):
        status, body = self._get("/api/home?project_id=missing-project")
        self.assertEqual(status, 404)
        self.assertIn("项目不存在", json.loads(body)["error"])

    def test_profile_evidence_rejects_invalid_offset(self):
        status, body = self._get("/api/profile/evidence?kind=feedback&offset=abc")
        self.assertEqual(status, 400)
        self.assertIn("分页", json.loads(body)["error"])

    def test_pdf_view_404_when_not_downloaded(self):
        status, body = self._get("/api/pdf/view?key=missing")
        self.assertEqual(status, 404)
        self.assertIn("error", json.loads(body))

    def test_pdf_view_serves_stored_file(self):
        app = server.make_app(str(self.root))
        app.store.upsert_papers([{"key": "pdf1", "title": "PDF Paper", "abstract": "x",
                                  "published": "2026-08-01", "group_name": "field"}])
        path = Path(self.root) / "sample.pdf"
        path.write_bytes(b"%PDF-1.4 test")
        app.store.record_pdf("pdf1", path, "local")
        status, body = self._get("/api/pdf/view?key=pdf1")
        self.assertEqual(status, 200)
        self.assertTrue(body.startswith(b"%PDF"))

    def test_qa_and_translate_dry_run_reserve_without_calling(self):
        app = server.make_app(str(self.root))
        app.store.upsert_papers([{"key": "q1", "title": "QA Paper", "abstract": "abstract text",
                                  "published": "2026-08-01", "group_name": "field"}])
        for route, body in (("/api/qa", {"key": "q1", "question": "why?", "dry_run": True}),
                            ("/api/translate", {"text": "latent prediction", "dry_run": True})):
            request = urllib.request.Request(
                f"http://127.0.0.1:{self.port}{route}",
                data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(request, timeout=5) as response:
                payload = json.loads(response.read())
            self.assertFalse(payload["ok"], route)
            self.assertTrue(payload["degraded"], route)
            self.assertIn("reservation", payload, route)
        # dry runs must not record history
        self.assertEqual(app.store.qa_history("q1"), [])

    def test_qa_history_endpoint(self):
        app = server.make_app(str(self.root))
        app.store.add_qa("q2", "user", "hello")
        app.store.add_qa("q2", "assistant", "hi")
        status, body = self._get("/api/qa?key=q2")
        self.assertEqual(status, 200)
        self.assertEqual([h["role"] for h in json.loads(body)["history"]], ["user", "assistant"])

    def test_vendored_pdfjs_is_served(self):
        status, body = self._get("/vendor/pdfjs/pdf.min.mjs")
        self.assertEqual(status, 200)
        self.assertTrue(len(body) > 1000)

    def test_feedback_round_trip_over_http(self):
        # Seed one paper directly so the UI has something to show.
        app = server.make_app(str(self.root))
        app.store.upsert_papers([
            {"key": "p1", "title": "World Model Paper", "abstract": "latent planning",
             "published": "2026-08-01", "group_name": "field"}])
        app.build_batch(limit=1)
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/feedback",
            data=json.dumps({"key": "p1", "action": "useful"}).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = json.loads(response.read())
        self.assertTrue(payload["interest_changed"])

    def test_understood_feedback_over_http_is_not_an_interest_change(self):
        app = server.make_app(str(self.root))
        app.store.upsert_papers([
            {"key": "p9", "title": "World Model Paper", "abstract": "latent planning",
             "published": "2026-08-01", "group_name": "field"}])
        app.build_batch(limit=1)
        app.store.save_to_library("p9", project_id=app.get_default_project_id())   # "understood" needs a saved paper
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/feedback",
            data=json.dumps({"key": "p9", "action": "understood"}).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = json.loads(response.read())
        self.assertEqual((payload["action"], payload["interest_changed"], payload["saved"]), ("understood", False, False))


if __name__ == "__main__":
    unittest.main()

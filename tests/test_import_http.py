"""Library import over HTTP: batches, streamed uploads, the background resolver, review and commit.

OpenAlex is replaced at the class, so the per-request apps and the worker thread all see the same fake."""
import http.client
import json
import threading
import time
import unittest
from unittest import mock
from urllib.parse import quote

from app import server, sources
from app.library_import import LibraryImport
from tests import test_app_server
from tests.library_import_fixtures import pdf, work


class ImportHTTPTests(unittest.TestCase):
    setUp = test_app_server.ServerSmokeTests.setUp

    def call(self, method, path, body=None, headers=None, raw=None):
        headers = dict(headers or {})
        data = raw
        if raw is None and body is not None:
            data = json.dumps(body).encode()
            headers.setdefault("Content-Type", "application/json")
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            connection.request(method, path, body=data, headers=headers)
            response = connection.getresponse()
            payload = response.read()
            try:
                return response.status, json.loads(payload)
            except ValueError:
                return response.status, payload
        finally:
            connection.close()

    def project(self):
        app = server.make_app(str(self.root))
        try:
            return app.projects.create_project("导入测试")
        finally:
            app.store.close()

    def new_batch(self, project=None, root="r", source="folder", **options):
        project = project or self.project()
        status, batch = self.call("POST", "/api/import/batches",
                                  {"project_id": project, "source": source, "root_name": root, "options": options})
        self.assertEqual(status, 200, batch)
        return project, batch["id"]

    def upload(self, batch, path, data, hints=None, modified=1700000000000, origin=None):
        headers = {"X-Relative-Path": quote(path), "X-Last-Modified": str(modified), "Content-Type": "application/pdf"}
        if hints is not None:
            headers["X-Import-Hints"] = quote(json.dumps(hints))
        if origin:
            headers["Origin"] = origin
        return self.call("POST", f"/api/import/batches/{batch}/pdf", headers=headers, raw=data)

    def wait(self, batch, states, seconds=15):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            status, detail = self.call("GET", f"/api/import/batches/{batch}")
            if detail["status"] in states:
                return detail
            time.sleep(0.05)
        self.fail(f"batch stayed {detail['status']}")


class BatchRouteTests(ImportHTTPTests):
    def test_creating_and_listing_a_batch(self):
        project, batch = self.new_batch()
        status, listed = self.call("GET", f"/api/import/batches?project_id={project}")
        self.assertEqual((status, [b["id"] for b in listed["batches"]]), (200, [batch]))
        status, detail = self.call("GET", f"/api/import/batches/{batch}")
        self.assertEqual((status, detail["status"], detail["counts"], detail["items"]), (200, "collecting", {}, []))
        self.assertIn("openalex", detail)
        self.assertFalse(detail["worker_alive"])

    def test_bad_requests_are_refused_with_a_reason(self):
        self.assertEqual(self.call("POST", "/api/import/batches", {"project_id": "nope", "source": "folder"})[0], 400)
        self.assertEqual(self.call("POST", "/api/import/batches", {"source": "folder"})[0], 400)
        self.assertEqual(self.call("GET", "/api/import/batches/unknown")[0], 400)
        self.assertEqual(self.call("GET", "/api/import/batches")[0], 400)  # a project is required
        self.assertEqual(self.call("POST", "/api/import/batches", [])[0], 400)

    def test_writes_from_another_site_are_refused(self):
        project = self.project()
        status, _ = self.call("POST", "/api/import/batches", {"project_id": project, "source": "files"},
                              headers={"Origin": "https://attacker.invalid"})
        self.assertEqual(status, 403)
        _, batch = self.new_batch(project)
        self.assertEqual(self.upload(batch, "r/a.pdf", pdf(1), origin="https://attacker.invalid")[0], 403)


class UploadRouteTests(ImportHTTPTests):
    def test_a_pdf_is_streamed_in_with_its_path_and_hints(self):
        _, batch = self.new_batch()
        status, item = self.upload(batch, "r/强化学习/论文 一.pdf", pdf(1), {"doi": "10.1000/x", "titles": ["A title"]})
        self.assertEqual(status, 200, item)
        self.assertEqual((item["state"], item["folders"], item["original_name"]), ("pending", [["强化学习"]], "论文 一.pdf"))
        self.assertEqual(item["hints"], {"doi": "10.1000/x", "titles": ["A title"]})
        _, detail = self.call("GET", f"/api/import/batches/{batch}")
        self.assertEqual(detail["counts"], {"pending": 1})
        self.assertEqual(detail["items"][0]["relative_path"], "r/强化学习/论文 一.pdf")

    def test_what_is_not_a_pdf_is_refused(self):
        _, batch = self.new_batch()
        status, body = self.upload(batch, "r/a.pdf", b"PK\x03\x04 zip bytes " * 20)
        self.assertEqual(status, 400)
        self.assertIn("PDF", body["error"])

    def test_a_declared_size_over_the_limit_is_refused_before_reading(self):
        _, batch = self.new_batch()
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            connection.putrequest("POST", f"/api/import/batches/{batch}/pdf")
            connection.putheader("X-Relative-Path", "r/a.pdf")
            connection.putheader("Content-Length", str(61 * 1024 * 1024))
            connection.endheaders()
            response = connection.getresponse()
            self.assertEqual(response.status, 413)
        finally:
            connection.close()

    def test_a_missing_or_malformed_path_is_refused(self):
        _, batch = self.new_batch()
        self.assertEqual(self.call("POST", f"/api/import/batches/{batch}/pdf", raw=pdf(1))[0], 400)
        self.assertEqual(self.upload(batch, "r/../../x.pdf", pdf(1))[0], 400)

    def test_the_resume_list_names_what_the_batch_already_holds(self):
        _, batch = self.new_batch()
        self.upload(batch, "r/a.pdf", pdf(1), modified=7)
        status, body = self.call("GET", f"/api/import/batches/{batch}?resume=1")
        self.assertEqual((status, body["files"]), (200, [["r/a.pdf", len(pdf(1)), 7]]))

    def test_sending_the_same_file_again_resumes_without_a_second_row(self):
        _, batch = self.new_batch()
        first = self.upload(batch, "r/a.pdf", pdf(1))[1]
        again = self.upload(batch, "r/a.pdf", pdf(1))
        self.assertEqual((again[0], again[1]["id"]), (200, first["id"]))
        self.assertEqual(self.call("GET", f"/api/import/batches/{batch}")[1]["counts"], {"pending": 1})
        self.assertEqual(self.upload(batch, "r/b.pdf", pdf(2))[0], 200)  # the server still answers normally afterwards


class ResolveCommitFlowTests(ImportHTTPTests):
    def test_upload_resolve_review_commit_puts_the_paper_in_the_library(self):
        project, batch = self.new_batch()
        self.upload(batch, "r/A/x.pdf", pdf(1), {"titles": ["Learning latent world models"]})
        self.upload(batch, "r/y.pdf", pdf(2), None)
        hit = work(1, "Learning latent world models")
        with mock.patch.object(sources.OpenAlex, "title_lookup", return_value=[hit]), \
                mock.patch.object(sources.OpenAlex, "rate_limit", return_value=None):
            status, started = self.call("POST", f"/api/import/batches/{batch}/resolve", {})
            self.assertEqual(status, 200)
            detail = self.wait(batch, {"review"})
        self.assertEqual(detail["counts"], {"matched": 1, "unmatched": 1})
        status, result = self.call("POST", f"/api/import/batches/{batch}/commit", {})
        self.assertEqual((status, result["result"]["new_papers"], result["result"]["unresolved"]), (200, 2, 1))
        _, library = self.call("GET", f"/api/library?project_id={project}")
        self.assertEqual(sorted(p["title"] for p in library["items"]), ["Learning latent world models", "y"])
        self.assertEqual(self.call("GET", f"/api/import/batches/{batch}")[1]["status"], "committed")

    def test_resolving_twice_does_not_start_two_workers(self):
        _, batch = self.new_batch()
        self.upload(batch, "r/x.pdf", pdf(1), {"titles": ["Learning latent world models"]})
        gate, release = threading.Event(), threading.Event()

        def slow(self_, title):
            gate.set()
            release.wait(10)
            return []
        with mock.patch.object(sources.OpenAlex, "title_lookup", slow), \
                mock.patch.object(sources.OpenAlex, "rate_limit", return_value=None):
            self.call("POST", f"/api/import/batches/{batch}/resolve", {})
            self.assertTrue(gate.wait(10))
            status, again = self.call("POST", f"/api/import/batches/{batch}/resolve", {})
            self.assertEqual((status, again["worker_alive"]), (200, True))
            self.assertTrue(self.call("GET", f"/api/import/batches/{batch}")[1]["worker_alive"])
            release.set()
            self.wait(batch, {"review"})

    def test_cancel_pauses_a_running_resolver(self):
        _, batch = self.new_batch()
        for i in range(3):
            self.upload(batch, f"r/x{i}.pdf", pdf(i), {"titles": [f"Learning latent world models {i}"]})
        gate, release = threading.Event(), threading.Event()

        def slow(self_, title):
            gate.set()
            release.wait(10)
            return []
        with mock.patch.object(sources.OpenAlex, "title_lookup", slow), \
                mock.patch.object(sources.OpenAlex, "rate_limit", return_value=None):
            self.call("POST", f"/api/import/batches/{batch}/resolve", {})
            self.assertTrue(gate.wait(10))
            self.assertEqual(self.call("POST", f"/api/import/batches/{batch}/cancel", {})[0], 200)
            release.set()
            detail = self.wait(batch, {"paused"})
        self.assertEqual(detail["pause_reason"], "cancelled")
        self.assertGreaterEqual(detail["counts"].get("pending", 0), 1)

    def test_online_lookup_off_makes_no_openalex_call(self):
        _, batch = self.new_batch(online=False)
        self.upload(batch, "r/x.pdf", pdf(1), {"doi": "10.1000/p1", "titles": ["Learning latent world models"]})
        with mock.patch.object(sources.OpenAlex, "_fetch", side_effect=AssertionError("network used")):
            self.call("POST", f"/api/import/batches/{batch}/resolve", {})
            detail = self.wait(batch, {"review"})
        self.assertEqual(detail["counts"], {"unmatched": 1})

    def test_review_actions_and_discard(self):
        _, batch = self.new_batch(online=False)
        self.upload(batch, "r/x.pdf", pdf(1))
        self.call("POST", f"/api/import/batches/{batch}/resolve", {})
        detail = self.wait(batch, {"review"})
        item = detail["items"][0]["id"]
        status, changed = self.call("POST", f"/api/import/batches/{batch}/items/{item}", {"action": "exclude"})
        self.assertEqual((status, changed["item"]["state"]), (200, "excluded"))
        self.assertEqual(self.call("POST", f"/api/import/batches/{batch}/items/{item}", {"action": "explode"})[0], 400)
        self.assertEqual(self.call("POST", f"/api/import/batches/{batch}/discard", {})[0], 200)
        self.assertEqual(self.call("GET", f"/api/import/batches/{batch}")[1]["status"], "discarded")
        self.assertEqual(self.upload(batch, "r/z.pdf", pdf(3))[0], 400)

    def test_the_review_can_ask_which_categories_the_folders_would_make(self):
        _, batch = self.new_batch(online=False)
        self.upload(batch, "r/强化学习/a.pdf", pdf(1))
        self.upload(batch, "r/强化学习/规划/b.pdf", pdf(2))
        self.call("POST", f"/api/import/batches/{batch}/resolve", {})
        self.wait(batch, {"review"})
        self.assertNotIn("categories", self.call("GET", f"/api/import/batches/{batch}")[1])
        preview = self.call("GET", f"/api/import/batches/{batch}?categories=1")[1]["categories"]
        self.assertEqual(sorted((tuple(p["path"]), p["count"]) for p in preview["paths"]),
                         [(("强化学习",), 1), (("强化学习", "规划"), 1)])
        self.assertEqual((preview["new_categories"], preview["over_ai_limit"]), (2, False))

    def test_when_the_allowance_is_used_up_the_rest_can_be_settled_and_committed(self):
        _, batch = self.new_batch()
        self.upload(batch, "r/x.pdf", pdf(1), {"titles": ["Learning latent world models"]})
        low = {"remaining": 0, "observed_at": time.time(), "reset_seconds": 3600}
        with mock.patch.object(sources.OpenAlex, "rate_limit", return_value=low):
            self.call("POST", f"/api/import/batches/{batch}/resolve", {})
            self.assertEqual(self.wait(batch, {"paused"})["pause_reason"], "openalex_quota")
        self.assertEqual(self.call("POST", f"/api/import/batches/{batch}/commit", {})[0], 400)
        status, body = self.call("POST", f"/api/import/batches/{batch}/settle", {})
        self.assertEqual((status, body["counts"]), (200, {"unmatched": 1}))
        self.assertEqual(self.call("GET", f"/api/import/batches/{batch}")[1]["status"], "review")
        self.assertEqual(self.call("POST", f"/api/import/batches/{batch}/commit", {})[0], 200)

    def test_a_batch_cannot_be_discarded_or_settled_while_it_is_being_matched(self):
        _, batch = self.new_batch()
        self.upload(batch, "r/x.pdf", pdf(1), {"titles": ["Learning latent world models"]})
        gate, release = threading.Event(), threading.Event()

        def slow(self_, title):
            gate.set()
            release.wait(10)
            return []
        with mock.patch.object(sources.OpenAlex, "title_lookup", slow), mock.patch.object(sources.OpenAlex, "rate_limit", return_value=None):
            self.call("POST", f"/api/import/batches/{batch}/resolve", {})
            self.assertTrue(gate.wait(10))
            self.assertEqual(self.call("POST", f"/api/import/batches/{batch}/discard", {})[0], 400)
            self.assertEqual(self.call("POST", f"/api/import/batches/{batch}/settle", {})[0], 400)
            release.set()
            self.wait(batch, {"review"})
        self.assertEqual(self.call("POST", f"/api/import/batches/{batch}/discard", {})[0], 200)

    def test_filtering_the_item_page_by_state(self):
        _, batch = self.new_batch(online=False)
        self.upload(batch, "r/x.pdf", pdf(1))
        self.call("POST", f"/api/import/batches/{batch}/resolve", {})
        self.wait(batch, {"review"})
        self.assertEqual(len(self.call("GET", f"/api/import/batches/{batch}?state=unmatched&limit=10")[1]["items"]), 1)
        self.assertEqual(self.call("GET", f"/api/import/batches/{batch}?state=matched")[1]["items"], [])


class CategoriesAndSeedsRouteTests(ImportHTTPTests):
    def committed_batch(self, **options):
        project, batch = self.new_batch(**options)
        self.upload(batch, "r/强化学习/规划/a.pdf", pdf(1), {"titles": ["Learning latent world models"]})
        self.upload(batch, "r/强化学习/b.pdf", pdf(2), {"titles": ["Planning with latent dynamics"]})
        hits = {"Learning latent world models": [work(1, "Learning latent world models")],
                "Planning with latent dynamics": [work(2, "Planning with latent dynamics")]}
        with mock.patch.object(sources.OpenAlex, "title_lookup", lambda self_, title: hits[title]), \
                mock.patch.object(sources.OpenAlex, "rate_limit", return_value=None):
            self.call("POST", f"/api/import/batches/{batch}/resolve", {})
            self.wait(batch, {"review"})
        self.assertEqual(self.call("POST", f"/api/import/batches/{batch}/commit", {})[0], 200)
        return project, batch

    def test_folders_become_categories_after_the_commit(self):
        _, batch = self.committed_batch()
        status, result = self.call("POST", f"/api/import/batches/{batch}/categories", {})
        self.assertEqual((status, result["result"]["created_categories"]), (200, 2))
        _, snapshot = self.call("GET", "/api/organization")
        self.assertEqual(sorted(d["name"] for d in snapshot["directions"]), ["强化学习", "规划"])
        self.assertEqual(snapshot["undo"]["label"], "导入分类")
        again = self.call("POST", f"/api/import/batches/{batch}/categories", {})[1]["result"]
        self.assertEqual(again["created_categories"], 0)

    def test_categories_before_the_commit_are_refused(self):
        _, batch = self.new_batch()
        self.assertEqual(self.call("POST", f"/api/import/batches/{batch}/categories", {})[0], 400)

    def test_imported_papers_can_be_made_seeds_and_taken_back(self):
        project, batch = self.committed_batch()
        key = "https://doi.org/10.1000/p1"
        status, result = self.call("POST", f"/api/import/batches/{batch}/seeds", {"action": "add", "keys": [key]})
        self.assertEqual((status, result["result"]["added"], result["result"]["seeds"]), (200, 1, 1))
        status, result = self.call("POST", f"/api/import/batches/{batch}/seeds", {"action": "remove", "keys": [key]})
        self.assertEqual((status, result["result"]["removed"], result["result"]["seeds"]), (200, 1, 0))

    def test_seed_requests_that_break_the_rules_are_refused(self):
        _, batch = self.committed_batch()
        for body in ({"action": "add", "keys": ["https://doi.org/10.1000/other"]}, {"action": "add", "keys": []},
                     {"action": "add"}, {"action": "explode", "keys": ["x"]}):
            self.assertEqual(self.call("POST", f"/api/import/batches/{batch}/seeds", body)[0], 400, body)


class SidecarRouteTests(ImportHTTPTests):
    BIB = (r"""@article{a,
	title = {Attention is all you need},
	author = {Vaswani, Ashish},
	year = {2017},
	doi = {10.5555/3295222.3295349},
	file = {PDF:files/12/Vaswani.pdf:application/pdf},
}
@article{c,
	title = {Only a reference},
	year = {2019},
	doi = {10.1000/ghost},
}
""").encode()

    def sidecar(self, batch, data=None, name="My Library.bib", origin=None):
        headers = {"X-Filename": quote(name), "Content-Type": "application/octet-stream"}
        if origin:
            headers["Origin"] = origin
        return self.call("POST", f"/api/import/batches/{batch}/sidecar", headers=headers, raw=self.BIB if data is None else data)

    def test_an_export_is_read_and_summarised(self):
        _, batch = self.new_batch(online=False)
        status, summary = self.sidecar(batch)
        self.assertEqual((status, summary["format"], summary["entries"], summary["with_files"]), (200, "bibtex", 2, 1))
        detail = self.call("GET", f"/api/import/batches/{batch}")[1]
        self.assertEqual(detail["sidecar"]["filename"], "My Library.bib")
        self.assertEqual(detail["counts"], {"pending": 2})

    def test_things_that_are_not_an_export_are_refused(self):
        _, batch = self.new_batch()
        self.assertEqual(self.sidecar(batch, b"nothing", "x.bib")[0], 400)
        self.assertEqual(self.sidecar(batch, name="x.txt")[0], 400)
        self.assertEqual(self.sidecar(batch, origin="https://attacker.invalid")[0], 403)
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            connection.putrequest("POST", f"/api/import/batches/{batch}/sidecar")
            connection.putheader("X-Filename", "big.bib")
            connection.putheader("Content-Length", str(21 * 1024 * 1024))
            connection.endheaders()
            self.assertEqual(connection.getresponse().status, 413)
        finally:
            connection.close()

    def test_zotero_export_flow_from_files_to_library(self):
        project, batch = self.new_batch(root="Export", source="zotero", online=False, include_fileless=True, root_category=True)
        self.sidecar(batch)
        self.upload(batch, "Export/files/12/Vaswani.pdf", pdf(1))
        self.call("POST", f"/api/import/batches/{batch}/resolve", {})
        detail = self.wait(batch, {"review"})
        self.assertEqual(detail["counts"], {"matched": 2})
        status, result = self.call("POST", f"/api/import/batches/{batch}/commit", {})
        self.assertEqual((status, result["result"]["new_papers"], result["result"]["pdfs_archived"]), (200, 2, 1))
        self.call("POST", f"/api/import/batches/{batch}/categories", {})
        _, library = self.call("GET", f"/api/library?project_id={project}")
        self.assertEqual(sorted(p["title"] for p in library["items"]), ["Attention is all you need", "Only a reference"])
        _, snapshot = self.call("GET", "/api/organization")
        self.assertEqual([d["name"] for d in snapshot["directions"]], ["Export"])


if __name__ == "__main__":
    unittest.main()

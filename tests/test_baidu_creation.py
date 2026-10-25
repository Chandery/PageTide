"""Project creation and seed search with Baidu Scholar. Offline only; the Baidu field names are UNVERIFIED (synthetic fixtures).

Candidates while creating a project (guidance_search / guidance_preview) and the manual seed picker (seed_search) ask Baidu
only when the user switched it on, a key is saved, and the text has Chinese characters (for candidates, also only when 中文 is
ticked). Baidu failures are a short status, never an error that breaks the page.
"""
import io
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
FIXTURES = ROOT / "tests" / "fixtures" / "baidu_scholar"
KEY = "bce-v3/ALTAK-dummyDummy0000/dummydummydummydummy0000"
DAILY_QUOTA = b'{"code":"18","message":"Open api daily request limit reached (synthetic)"}'      # a 429 that names the daily allowance
DOI_1 = "https://doi.org/10.1234/kg.2024.001"
PAGE_1 = "https://xueshu.baidu.com/usercenter/paper/show?paperid=synthetic-p1"


def fixture(name):
    return (FIXTURES / name).read_bytes()


class Reply:
    def __init__(self, body):
        self.body, self.headers = body, {}

    def read(self, limit=-1):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def openalex_work(n, title, doi=None):
    return {"id": f"https://openalex.org/W{n}", "doi": doi or f"https://doi.org/10.9/{n}", "title": title, "publication_date": "2024-03-01",
            "type": "article", "ids": {}, "primary_location": {"source": {"display_name": "Journal"}}, "abstract_inverted_index": {"graph": [0], "survey": [1]}}


class Net:
    def __init__(self):
        self.baidu, self.openalex = [], []
        self.baidu_answer = fixture("success.json")
        self.baidu_error = None
        self.openalex_results = []
        self.openalex_error = None
        self.lock = threading.Lock()

    def __call__(self, request, timeout=None):
        url = request.full_url
        if "qianfan.baidubce.com" in url:
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
            with self.lock:
                self.baidu.append({"wd": query["wd"][0], "page": int(query["pageNum"][0]), "auth": request.get_header("Authorization")})
            if self.baidu_error:
                raise self.baidu_error
            return Reply(self.baidu_answer)
        if "api.openalex.org" in url:
            with self.lock:
                self.openalex.append(url)
            if self.openalex_error:
                raise self.openalex_error
            return Reply(json.dumps({"results": self.openalex_results}).encode())
        raise AssertionError("unexpected request: " + url)


class Case(unittest.TestCase):
    def setUp(self):
        from tests.recommendation_fixtures import set_user_settings
        self.set_user_settings = set_user_settings
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / "harness").mkdir()
        (self.root / "harness" / "seeds.json").write_text(json.dumps({"seeds": []}))
        (self.root / "app").mkdir(exist_ok=True)
        (self.root / "app" / "budget.json").write_text((ROOT / "app" / "budget.json").read_text())
        patcher = mock.patch.dict(os.environ, {}, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop("BAIDU_SCHOLAR_API_KEY", None)
        os.environ["OPENALEX_API_KEY"] = "test-openalex-key-0000"  # OpenAlex is only searched with a key
        sleeper = mock.patch("time.sleep")
        sleeper.start()
        self.addCleanup(sleeper.stop)
        from app import creation
        creation._SEED_CACHE.clear()
        from app.service import App
        self.app = App(root=str(self.root), data_dir=str(self.root / "data"))
        self.addCleanup(self.app.store.close)
        self.set_user_settings(self.app, timePreference="all", sourceBaiduScholar=True)
        self.app.save_source_key("baidu_scholar", KEY)
        self.net = Net()

    def session(self):
        return self.app.create_guidance_session("知识图谱", "了解知识图谱的构建方法", "ai_guided")["id"]

    def patched(self):
        return mock.patch.object(urllib.request, "urlopen", self.net)

    def search(self, query="知识图谱", languages=("zh", "en"), **kwargs):
        sid = kwargs.pop("session_id", None) or self.session()
        with self.patched():
            return self.app.guidance_search(sid, query, languages=list(languages) if languages is not None else None, **kwargs), sid


class GuidanceSearchTests(Case):
    def test_a_chinese_query_with_chinese_ticked_adds_baidu_candidates(self):
        result, sid = self.search()
        self.assertEqual([c["wd"] for c in self.net.baidu], ["知识图谱"])
        self.assertEqual(self.net.baidu[0]["auth"], f"Bearer {KEY}")
        titles = [i["title"] for i in result["items"]]
        self.assertIn("知识图谱 构建方法综述", titles)
        first = next(i for i in result["items"] if i["key"] == DOI_1)
        self.assertEqual((first["matched_queries"], first["new"], first["url"], first["pdf_status"]), (["知识图谱"], True, DOI_1, "page"))
        self.assertNotIn("baidu", result)
        stored = {p["key"]: p for p in self.app.store.guidance_session(sid)["draft"]["candidates"]}
        self.assertEqual(stored[DOI_1]["oa"]["pages"][0]["url"], PAGE_1)
        self.assertNotIn(KEY, json.dumps(self.app.store.guidance_session(sid)["draft"]))

    def test_no_baidu_unless_every_condition_holds(self):
        cases = {"zh not ticked": dict(languages=["en"]), "no languages sent": dict(languages=None), "empty languages": dict(languages=[]),
                 "english query": dict(query="knowledge graph")}
        for name, kwargs in cases.items():
            self.net.baidu.clear()
            self.search(**kwargs)
            self.assertEqual(self.net.baidu, [], name)
        self.set_user_settings(self.app, sourceBaiduScholar=False)
        self.search()
        self.assertEqual(self.net.baidu, [], "switch off")
        self.set_user_settings(self.app, sourceBaiduScholar=True)
        self.app.clear_source_key("baidu_scholar")
        self.search()
        self.assertEqual(self.net.baidu, [], "no key")

    def test_a_query_mixing_scripts_counts_as_chinese(self):
        self.search(query="知识图谱 knowledge graph")
        self.assertEqual(len(self.net.baidu), 1)

    def test_openalex_candidates_are_still_found_and_a_shared_doi_is_one_candidate_with_the_baidu_page(self):
        self.net.openalex_results = [openalex_work(1, "Knowledge graph survey", doi=DOI_1), openalex_work(2, "Another survey")]
        result, sid = self.search()
        by_key = {i["key"]: i for i in result["items"]}
        self.assertIn("https://doi.org/10.9/2", by_key)
        self.assertEqual(len([i for i in result["items"] if i["key"] == DOI_1]), 1)
        self.assertEqual(by_key[DOI_1]["title"], "Knowledge graph survey")                  # the OpenAlex entry stays, with the page added
        stored = {p["key"]: p for p in self.app.store.guidance_session(sid)["draft"]["candidates"]}
        self.assertEqual(stored[DOI_1]["oa"]["pages"][0]["url"], PAGE_1)
        self.assertEqual(by_key[DOI_1]["pdf_status"], "page")

    def test_the_same_query_twice_adds_nothing_new_and_spends_no_second_call(self):
        result, sid = self.search()
        again, _ = self.search(session_id=sid)
        self.assertEqual(len(self.net.baidu), 1)                     # the second answer comes from the 24 h cache
        self.assertTrue(all(not i["new"] for i in again["items"]))

    def test_all_years_removes_the_year_floor_and_the_default_keeps_the_window(self):
        self.net.baidu_answer = json.dumps({"code": "0", "data": [
            {"paperId": "old1", "title": "很早以前发表的中文论文", "abstract": "旧摘要内容。", "doi": "", "keyword": "kg", "publishYear": 2005,
             "publishInfo": {"journalName": "J"}, "url": "https://xueshu.baidu.com/p/old1"},
            {"paperId": "new1", "title": "最近发表的中文论文题目", "abstract": "新摘要内容。", "doi": "", "keyword": "kg", "publishYear": 2024,
             "publishInfo": {"journalName": "J"}, "url": "https://xueshu.baidu.com/p/new1"}]}).encode()
        default, _ = self.search(query="知识图谱默认")
        everything, _ = self.search(query="知识图谱全部", all_years=True)
        self.assertEqual([i["published"] for i in default["items"]], ["2024-01-01"])
        self.assertEqual(sorted(i["published"] for i in everything["items"]), ["2005-01-01", "2024-01-01"])

    def test_a_baidu_failure_is_a_short_status_and_the_page_still_gets_openalex_results(self):
        self.net.openalex_results = [openalex_work(2, "Another survey")]
        for error, kind in ((urllib.error.HTTPError("https://qianfan.baidubce.com/x", 401, "no", {}, None), "auth_required"),
                            (urllib.error.HTTPError("https://qianfan.baidubce.com/x", 429, "no", {}, io.BytesIO(DAILY_QUOTA)), "quota_exhausted"),
                            (urllib.error.URLError("offline " + KEY), "network_error")):
            self.net.baidu_error = error
            result, _ = self.search(query=f"知识图谱{kind}")
            self.assertEqual(result["baidu"], {"kind": kind})
            self.assertIsNone(result["error"])
            self.assertEqual([i["key"] for i in result["items"]], ["https://doi.org/10.9/2"])
            self.assertNotIn(KEY, json.dumps(result))

    def test_the_local_cap_is_a_quota_status_and_makes_no_call(self):
        import datetime
        day = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=8)).date().isoformat()
        self.app.store.conn.execute("INSERT INTO settings(key,value) VALUES(?,?)", ("source_usage:baidu_scholar:" + day, "40"))
        self.app.store.conn.commit()
        result, _ = self.search()
        self.assertEqual((self.net.baidu, result["baidu"]), ([], {"kind": "quota_exhausted"}))

    def test_an_openalex_failure_is_unchanged_and_baidu_results_still_come(self):
        self.net.openalex_error = urllib.error.URLError("offline")
        # An OpenAlex outage hands the search to arXiv's API; when that is down as well, the error still reaches the page.
        self.app.source.arxiv = mock.Mock(discover_topic=mock.Mock(side_effect=__import__("app.sources", fromlist=["x"]).SourceError("arXiv offline", "network_error")))
        result, _ = self.search()
        self.assertEqual(result["error"]["kind"], "network_error")
        self.assertIn(DOI_1, [i["key"] for i in result["items"]])

    def test_candidates_stay_within_their_limit_and_survive_creating_the_project(self):
        result, sid = self.search()
        chosen = [DOI_1, "baidu:synthetic-p2"]
        created = self.app.finalize_guidance(sid, selected_keys=chosen, language_policy={"allowed_languages": ["zh"]}, skip_route=True)
        self.assertEqual(created["selected"], 2)
        row = self.app.store.paper(DOI_1)
        self.assertEqual(json.loads(row["oa_json"])["via"], ["baidu_scholar"])
        self.assertEqual(self.app.store.conn.execute("SELECT relation_kind FROM project_papers WHERE project_id=? AND paper_key=?",
                                                     (created["project_id"], DOI_1)).fetchone()[0], "imported")


class GuidancePreviewTests(Case):
    def test_preview_passes_the_languages_to_every_query(self):
        sid = self.session()
        draft = {"keywords": ["知识图谱", "knowledge graph"], "search_queries": ["知识图谱 综述", "knowledge graph survey"]}
        with self.patched():
            result = self.app.guidance_preview(sid, draft, languages=["zh", "en"])
        self.assertEqual([c["wd"] for c in self.net.baidu], ["知识图谱 综述"])
        self.assertTrue(any(i["key"] == DOI_1 for i in result["items"]))
        self.net.baidu.clear()
        with self.patched():
            self.app.guidance_preview(sid, draft, languages=["en"])
        self.assertEqual(self.net.baidu, [])

    def test_a_baidu_status_is_reported_without_an_error_entry(self):
        sid = self.session()
        self.net.baidu_error = urllib.error.HTTPError("https://qianfan.baidubce.com/x", 401, "no", {}, None)
        with self.patched():
            result = self.app.guidance_preview(sid, {"keywords": ["知识图谱"], "search_queries": ["知识图谱"]}, languages=["zh"])
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["baidu"], {"kind": "auth_required"})


class SeedSearchTests(Case):
    def seed_search(self, query="知识图谱构建"):
        with self.patched():
            return self.app.seed_search(query)

    def test_a_chinese_title_search_adds_ranked_baidu_hits_that_can_be_added(self):
        self.net.openalex_results = [openalex_work(5, "Knowledge graph embedding")]
        result = self.seed_search("知识图谱构建方法综述")
        self.assertEqual(result["status"], "ok")
        self.assertEqual([c["wd"] for c in self.net.baidu], ["知识图谱构建方法综述"])
        keys = [i["key"] for i in result["items"]]
        self.assertEqual(keys[0], DOI_1)                                   # the closest title first, whichever source found it
        self.assertIn("https://doi.org/10.9/5", keys)
        first = result["items"][0]
        self.assertEqual((first["seed_id"], first["url"]), (DOI_1, DOI_1))
        self.assertEqual(next(i for i in result["items"] if i["key"] == "baidu:synthetic-p2")["seed_id"], "baidu:synthetic-p2")
        self.assertNotIn("seed_id", next(i for i in result["items"] if i["key"] == "https://doi.org/10.9/5"))
        self.assertNotIn("baidu", result)

    def test_a_title_the_page_read_out_of_a_dropped_pdf_is_not_sent_to_baidu(self):
        with self.patched():
            result = self.app.seed_search("知识图谱构建方法综述", typed=False)
        self.assertEqual(self.net.baidu, [])
        self.assertNotIn("baidu", result)
        with self.patched():
            self.app.seed_search("知识图谱构建方法综述", typed=True)
        self.assertEqual(len(self.net.baidu), 1)

    def test_no_baidu_for_english_text_or_when_off_or_without_a_key(self):
        self.seed_search("knowledge graph embedding")
        self.assertEqual(self.net.baidu, [])
        self.set_user_settings(self.app, sourceBaiduScholar=False)
        self.seed_search()
        self.assertEqual(self.net.baidu, [])
        self.set_user_settings(self.app, sourceBaiduScholar=True)
        self.app.clear_source_key("baidu_scholar")
        self.seed_search()
        self.assertEqual(self.net.baidu, [])

    def test_a_baidu_failure_never_breaks_the_search(self):
        self.net.openalex_results = [openalex_work(5, "知识图谱 embedding")]
        self.net.baidu_error = urllib.error.HTTPError("https://qianfan.baidubce.com/x", 429, "no", {}, io.BytesIO(DAILY_QUOTA))
        result = self.seed_search()
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["baidu"], {"kind": "quota_exhausted"})
        self.assertEqual([i["key"] for i in result["items"]], ["https://doi.org/10.9/5"])

    def test_baidu_alone_answers_when_openalex_is_down_and_a_failure_of_both_is_reported(self):
        self.net.openalex_error = urllib.error.URLError("offline")
        result = self.seed_search()
        self.assertEqual(result["status"], "ok")
        self.assertIn(DOI_1, [i["key"] for i in result["items"]])
        self.net.baidu_error = urllib.error.HTTPError("https://qianfan.baidubce.com/x", 401, "no", {}, None)
        result = self.seed_search("信息抽取方法")
        self.assertEqual(result["items"], [])
        self.assertEqual(result["status"], "network_error")                  # OpenAlex's own failure still decides the status
        self.assertEqual(result["baidu"], {"kind": "auth_required"})
        self.assertNotIn(KEY, json.dumps(result))

    def test_nothing_found_anywhere_is_empty_not_an_error(self):
        self.net.baidu_answer = fixture("empty.json")
        result = self.seed_search()
        self.assertEqual((result["status"], result["items"]), ("empty", []))

    def test_a_chinese_query_shorter_than_three_characters_is_still_refused_as_before(self):
        with self.patched():
            with self.assertRaises(ValueError):
                self.app.seed_search("图谱")
        self.assertEqual(self.net.baidu, [])


class SeedAdoptionTests(Case):
    def hit(self, key):
        with self.patched():
            items = self.app.seed_search("知识图谱构建方法综述")["items"]
        return next(i for i in items if i["key"] == key)

    def test_identifiers_of_remembered_baidu_hits_parse(self):
        from app import creation
        self.assertEqual(creation.parse_seed("baidu:synthetic-p2"), ("baidu:synthetic-p2", None, "baidu:synthetic-p2"))
        for bad in ("baidu:", "baidu:has space", "baidu:" + "x" * 200, "baidu:<script>"):
            with self.assertRaises(ValueError):
                creation.parse_seed(bad)
        with self.assertRaises(ValueError):
            creation.parse_seed("知识图谱构建方法综述")

    def test_a_hit_without_a_doi_becomes_a_seed_from_what_baidu_said(self):
        self.hit("baidu:synthetic-p2")
        result = self.app.create_project("中文种子", "manual", ["数字人文"], ["baidu:synthetic-p2"], language_policy={"allowed_languages": ["zh"]})
        self.assertEqual([(r["status"], r["key"]) for r in result["seed_results"]], [("resolved", "baidu:synthetic-p2")])
        pid = result["project_id"]
        self.assertEqual(self.app.seed_keys(pid), ["baidu:synthetic-p2"])
        self.assertEqual(self.app.store.paper("baidu:synthetic-p2")["title"], "数字人文研究进展")

    def test_a_hit_with_a_doi_openalex_does_not_know_falls_back_to_the_remembered_hit(self):
        self.hit(DOI_1)
        client = mock.Mock()
        from app.sources import SourceError
        client.work.side_effect = SourceError("no record", "not_found")
        self.app.source = client
        result = self.app.create_project("有 DOI 的种子", "manual", [], [DOI_1], language_policy={"allowed_languages": ["zh"]})
        self.assertEqual([r["status"] for r in result["seed_results"]], ["resolved"])
        self.assertEqual(self.app.seed_keys(result["project_id"]), [DOI_1])
        client.work.assert_called_once()

    def test_openalex_wins_when_it_knows_the_doi(self):
        self.hit(DOI_1)
        client = mock.Mock()
        client.work.return_value = openalex_work(9, "OpenAlex's own title", doi=DOI_1)
        self.app.source = client
        result = self.app.create_project("OpenAlex 优先", "manual", [], [DOI_1], language_policy={"allowed_languages": ["zh"]})
        self.assertEqual(self.app.store.paper(DOI_1)["title"], "OpenAlex's own title")
        self.assertEqual([r["status"] for r in result["seed_results"]], ["resolved"])

    def test_an_identifier_never_searched_for_is_not_found_and_does_not_break_creation(self):
        result = self.app.create_project("没搜过", "manual", ["数字人文"], ["baidu:never-seen", "baidu:also-never"], language_policy={"allowed_languages": ["zh"]})
        self.assertEqual([r["status"] for r in result["seed_results"]], ["not_found", "not_found"])
        self.assertTrue(result["project_id"])

    def test_the_same_hit_twice_is_one_seed(self):
        self.hit("baidu:synthetic-p2")
        result = self.app.create_project("重复", "manual", [], ["baidu:synthetic-p2", "baidu:synthetic-p2"], language_policy={"allowed_languages": ["zh"]})
        self.assertEqual([r["status"] for r in result["seed_results"]], ["resolved", "duplicate"])


class RouteTests(Case):
    def serve(self):
        from app import server
        patcher = mock.patch.dict(os.environ, {"PAGETIDE_DATA": str(self.root / "data")})      # the server reads this app's data
        patcher.start()
        self.addCleanup(patcher.stop)
        httpd = server.build_server(port=0, root=str(self.root))
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        return httpd.server_address[1]

    def post(self, port, path, payload):
        real = urllib.request.urlopen
        request = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=json.dumps(payload).encode(),
                                         headers={"Content-Type": "application/json"}, method="POST")

        def router(req, timeout=None):
            return real(req, timeout=timeout) if req.full_url.startswith("http://127.0.0.1") else self.net(req, timeout)
        with mock.patch.object(urllib.request, "urlopen", router):
            with real(request, timeout=10) as response:
                return json.loads(response.read().decode())

    def test_the_routes_pass_the_languages_on(self):
        port = self.serve()
        sid = self.session()
        body = self.post(port, f"/api/project-guidance/sessions/{sid}/search", {"query": "知识图谱", "languages": ["zh"]})
        self.assertEqual(len(self.net.baidu), 1)
        self.assertTrue(any(i["key"] == DOI_1 for i in body["items"]))
        self.net.baidu.clear()
        self.post(port, f"/api/project-guidance/sessions/{sid}/search", {"query": "信息抽取", "languages": ["en"]})
        self.post(port, f"/api/project-guidance/sessions/{sid}/search", {"query": "信息抽取"})
        self.assertEqual(self.net.baidu, [])
        self.post(port, f"/api/project-guidance/sessions/{sid}/preview", {"draft": {"keywords": ["数字人文"], "search_queries": ["数字人文"]}, "languages": ["zh"]})
        self.assertEqual([c["wd"] for c in self.net.baidu], ["数字人文"])

    def test_the_seed_route_sends_only_typed_text_to_baidu(self):
        port = self.serve()
        self.post(port, "/api/seeds/search", {"query": "知识图谱构建方法", "typed": False})
        self.assertEqual(self.net.baidu, [])
        self.post(port, "/api/seeds/search", {"query": "知识图谱构建方法", "typed": True})
        self.post(port, "/api/seeds/search", {"query": "信息抽取方法研究"})
        self.assertEqual(len(self.net.baidu), 2)

    def test_the_seed_route_returns_the_baidu_note(self):
        port = self.serve()
        self.net.baidu_error = urllib.error.HTTPError("https://qianfan.baidubce.com/x", 401, "no", {}, None)
        body = self.post(port, "/api/seeds/search", {"query": "知识图谱构建方法"})
        self.assertEqual(body["baidu"], {"kind": "auth_required"})

# The Baidu Scholar interface is not offered any more (app.user_settings.BAIDU_SCHOLAR_OFFERED); these tests exercise the
# adapter itself, so the offer is switched on for this module only.
_OFFER_SCHOLAR = __import__("unittest.mock", fromlist=["patch"]).patch.object(
    __import__("app.user_settings", fromlist=["x"]), "BAIDU_SCHOLAR_OFFERED", True)


def setUpModule():
    _OFFER_SCHOLAR.start()


def tearDownModule():
    _OFFER_SCHOLAR.stop()


if __name__ == "__main__":
    unittest.main()

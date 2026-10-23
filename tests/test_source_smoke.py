"""tools/source_smoke.py: the real-key smoke test the coordinator runs once. Only its pure parts are tested here (no network)."""
import json
import os
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
FIXTURES = ROOT / "tests" / "fixtures" / "baidu_scholar"
DUMMY = "bce-v3/ALTAK-dummyDummy0000/dummydummydummydummy0000"


class SmokeTests(unittest.TestCase):
    def setUp(self):
        import source_smoke
        self.smoke = source_smoke

    def test_the_key_description_never_contains_the_key(self):
        text = json.dumps(self.smoke.describe_key(DUMMY))
        for part in (DUMMY, "ALTAK", "dummyDummy", "dummydummy"):
            self.assertNotIn(part, text)
        info = self.smoke.describe_key(DUMMY)
        self.assertEqual(info["segments"], 3)
        self.assertEqual(info["lengths"], [len(part) for part in DUMMY.split("/")])
        self.assertIn("/", info["punctuation"])
        self.assertEqual(info["first_segment"], "bce-v3")

    def test_a_long_or_odd_first_segment_is_not_printed(self):
        self.assertIsNone(self.smoke.describe_key("ALTAKSECRETSECRETSECRET/abc")["first_segment"])
        self.assertIsNone(self.smoke.describe_key("a" * 30)["first_segment"])

    def test_the_summary_reports_shape_and_not_content(self):
        payload = json.loads((FIXTURES / "success.json").read_text(encoding="utf-8"))
        lines = self.smoke.summarise(200, payload)
        text = "\n".join(lines)
        self.assertIn("HTTP 200", text)
        self.assertIn("code", text)
        self.assertIn("items: 7", text)
        self.assertIn("hasMore: True", text)
        self.assertIn("aiAbstract returned by default: yes", text)
        self.assertIn("publishYear types: int, str", text)
        self.assertIn("with doi: 2", text)
        self.assertIn("https page link: ", text)
        self.assertIn("parsed by app: 5", text)
        self.assertNotIn("AI-GENERATED-SUMMARY", text)          # the summary shows names and counts, never paper text
        self.assertNotIn("知识图谱构建", text)

    def test_the_summary_of_an_error_body(self):
        payload = json.loads((FIXTURES / "error_auth.json").read_text(encoding="utf-8"))
        text = "\n".join(self.smoke.summarise(401, payload))
        self.assertIn("HTTP 401", text)
        self.assertIn("kind from the app's parser: auth_required", text)
        self.assertNotIn("not-a-dict", text)
        self.assertIn("not a JSON object", "\n".join(self.smoke.summarise(502, None)))

    def test_message_text_is_shortened_and_key_free(self):
        payload = {"code": "110", "message": "bad " + DUMMY + " " + "x" * 300}
        text = "\n".join(self.smoke.summarise(401, payload, key=DUMMY))
        self.assertNotIn(DUMMY, text)
        self.assertLess(max(len(line) for line in text.split("\n")), 200)

    def test_the_wrong_key_is_a_fixed_dummy_and_the_key_comes_from_the_env_or_file(self):
        self.assertNotIn("bce", self.smoke.WRONG_KEY)
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("BAIDU_SCHOLAR_API_KEY", None)
            self.assertIsNone(self.smoke.find_key(Path(tmp)))
            (Path(tmp) / "baidu_scholar.key").write_text(f"BAIDU_SCHOLAR_API_KEY={DUMMY}\n")
            self.assertEqual(self.smoke.find_key(Path(tmp)), (DUMMY, "key file"))
            with mock.patch.dict(os.environ, {"BAIDU_SCHOLAR_API_KEY": "from-env/0123456789"}):
                self.assertEqual(self.smoke.find_key(Path(tmp)), ("from-env/0123456789", "environment"))

    def test_no_network_when_the_key_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("BAIDU_SCHOLAR_API_KEY", None)
            printed = []
            with mock.patch("urllib.request.urlopen", side_effect=AssertionError("no request without a key")), \
                    mock.patch("builtins.print", side_effect=lambda *a, **k: printed.append(" ".join(map(str, a)))):
                self.assertEqual(self.smoke.main(["baidu_scholar", "--data-dir", tmp]), 2)
            self.assertIn("Nothing was sent", printed[0])

    def test_a_run_saves_the_raw_answer_under_local_and_prints_no_key(self):
        body = (FIXTURES / "success.json").read_bytes()

        class Reply:
            status = 200
            headers = {}

            def read(self, limit=-1):
                return body

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"BAIDU_SCHOLAR_API_KEY": DUMMY}):
            out = Path(tmp) / "raw"
            printed = []
            with mock.patch("urllib.request.urlopen", return_value=Reply()) as opened, mock.patch("builtins.print", side_effect=lambda *a, **k: printed.append(" ".join(map(str, a)))):
                code = self.smoke.main(["baidu_scholar", "--query", "知识图谱", "--data-dir", tmp, "--raw-dir", str(out)])
            self.assertEqual(code, 0)
            request = opened.call_args.args[0]
            self.assertEqual(request.get_header("Authorization"), f"Bearer {DUMMY}")
            self.assertNotIn(DUMMY, request.full_url)
            self.assertNotIn("enable_ai_abstract", request.full_url)
            saved = list(out.glob("baidu_scholar-*.json"))
            self.assertEqual(len(saved), 1)
            self.assertNotIn(DUMMY, saved[0].read_text(encoding="utf-8"))
            self.assertNotIn(DUMMY, "\n".join(printed))

    def test_an_http_error_is_summarised_not_raised(self):
        error = urllib.error.HTTPError("https://qianfan.baidubce.com/x", 401, "no", {}, None)
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"BAIDU_SCHOLAR_API_KEY": DUMMY}):
            printed = []
            with mock.patch("urllib.request.urlopen", side_effect=error), mock.patch("builtins.print", side_effect=lambda *a, **k: printed.append(" ".join(map(str, a)))):
                code = self.smoke.main(["baidu_scholar", "--wrong-key", "--data-dir", tmp, "--raw-dir", str(Path(tmp) / "raw")])
            self.assertEqual(code, 1)
            self.assertIn("HTTP 401", "\n".join(printed))


if __name__ == "__main__":
    unittest.main()

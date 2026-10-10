"""Project guidance explains output truncation without blaming a short user input."""
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app.service import App


ROOT = Path(__file__).resolve().parents[1]
GOAL = "Agent安全相关的"


def provider_payload(*, usage=True):
    payload = {
        "choices": [{"message": {"content": '{"r":"'}, "finish_reason": "length"}],
    }
    if usage:
        payload["usage"] = {"prompt_tokens": 177, "completion_tokens": 500, "total_tokens": 677}
    return io.BytesIO(json.dumps(payload).encode())


class GuidanceTruncationTests(unittest.TestCase):
    def run_actual_gateway(self, *, usage):
        with tempfile.TemporaryDirectory() as folder, mock.patch.dict(os.environ, {
                "DEEPSEEK_API_KEY": "synthetic-guidance-truncation", "PDH_DEV": "0"}), \
                mock.patch("app.gateway.urllib.request.urlopen",
                           return_value=provider_payload(usage=usage)) as sent:
            app = App(root=ROOT, data_dir=Path(folder))
            self.addCleanup(app.store.close)
            session = app.create_guidance_session("Synthetic project", GOAL)
            result = app.guidance_turn(session["id"], GOAL)
            return result, session, sent

    def assert_length_reason(self, result):
        self.assertEqual(result["mode"], "local")
        self.assertEqual(result["reason_code"], "bad_reply")
        self.assertIn("输出长度", result["reason"])
        self.assertNotIn("缩短输入", result["reason"])
        self.assertEqual(result["session"]["turn_count"], 0)
        self.assertEqual(result["session"]["draft"]["goal"], GOAL)

    def test_gateway_known_usage_explains_length_and_does_not_retry(self):
        result, _session, sent = self.run_actual_gateway(usage=True)
        self.assertEqual(sent.call_count, 1)
        self.assert_length_reason(result)
        self.assertFalse(result["usage_unknown"])
        self.assertFalse(result["usage_reserved"])
        self.assertEqual(result["usage"]["total_tokens"], 677)

    def test_gateway_unknown_usage_explains_length_and_keeps_reservation(self):
        result, _session, sent = self.run_actual_gateway(usage=False)
        self.assertEqual(sent.call_count, 1)
        self.assert_length_reason(result)
        self.assertTrue(result["usage_unknown"])
        self.assertTrue(result["usage_reserved"])
        self.assertEqual(result["usage"]["total_tokens"], 1700)

    def test_parse_length_branch_keeps_specific_reason_instead_of_generic_bad_reply(self):
        with tempfile.TemporaryDirectory() as folder:
            app = App(root=ROOT, data_dir=Path(folder))
            self.addCleanup(app.store.close)
            session = app.create_guidance_session("Synthetic project", GOAL)
            with mock.patch.object(app.gateway, "call", return_value={
                    "ok": True, "content": '{"r":"', "finish_reason": "length",
                    "usage": {"prompt_tokens": 177, "completion_tokens": 500, "total_tokens": 677},
                    "usage_unknown": False, "usage_reserved": False}):
                result = app.guidance_turn(session["id"], GOAL)
            self.assert_length_reason(result)
            self.assertFalse(result["usage_unknown"])
            self.assertFalse(result["usage_reserved"])


if __name__ == "__main__":
    unittest.main()

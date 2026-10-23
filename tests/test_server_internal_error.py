"""An unexpected exception in a handler answers 500 and is logged; it no longer drops the connection."""
import io
import json
import unittest
import urllib.error
import urllib.request
from contextlib import redirect_stderr
from unittest import mock

from tests import test_app_server
from app import server


class InternalErrorTests(unittest.TestCase):
    setUp = test_app_server.ServerSmokeTests.setUp

    def test_unexpected_exception_returns_500_and_the_server_keeps_serving(self):
        request = urllib.request.Request(f"http://127.0.0.1:{self.port}/api/route",
                                         data=json.dumps({"action": "candidates"}).encode(),
                                         headers={"Content-Type": "application/json"}, method="POST")
        log = io.StringIO()
        with mock.patch("app.service.App.route_candidates", side_effect=RuntimeError("boom")), redirect_stderr(log):
            with self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(request, timeout=5)
        self.assertEqual(caught.exception.code, 500)
        self.assertEqual(json.loads(caught.exception.read()), {"error": "internal error"})
        caught.exception.close()
        self.assertIn("RuntimeError: boom", log.getvalue())
        self.assertEqual(self._get("/api/state")[0], 200)

    _get = test_app_server.ServerSmokeTests._get


if __name__ == "__main__":
    unittest.main()

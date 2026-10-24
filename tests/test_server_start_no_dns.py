"""The local server starts without a reverse DNS lookup. http.server.HTTPServer.server_bind calls
socket.getfqdn(host); on GitHub's macOS runners getfqdn("127.0.0.1") took 35 s (measured 2026-10-25), and a Mac
with a slow resolver would make the app wait the same at every launch. The name it finds is never used."""
import socket
import tempfile
import unittest
from unittest import mock

from app import server


class ServerStartTests(unittest.TestCase):
    def test_build_server_never_resolves_the_loopback_name(self):
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(socket, "getfqdn", side_effect=AssertionError("reverse DNS at start")) as getfqdn:
            httpd = server.build_server(port=0, root=tmp)
            try:
                host, port = httpd.server_address[:2]
                self.assertEqual((httpd.server_name, httpd.server_port), (host, port))
                self.assertEqual(host, "127.0.0.1")
                self.assertGreater(port, 0)
            finally:
                httpd.server_close()
        getfqdn.assert_not_called()


if __name__ == "__main__":
    unittest.main()

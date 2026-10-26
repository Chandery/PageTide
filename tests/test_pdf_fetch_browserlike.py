"""PDF downloads that a browser manages and the app used to call "network problem" (2026-10-26).

A link with Chinese characters in its path, a site that leaves out an intermediate certificate, a robots.txt moved to
plain http. No test touches the network: the seams are patched.
"""
import ssl
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import pdf_fetch  # noqa: E402


def issuer_missing():
    reason = ssl.SSLCertVerificationError(1, "certificate verify failed: unable to get local issuer certificate")
    reason.verify_code = 20
    return urllib.error.URLError(reason)


class LinkTests(unittest.TestCase):
    def test_non_ascii_path_is_percent_encoded_like_a_browser(self):
        url = "https://cjl.lightpublishing.cn/rc-pub/front/front-article/download/129680071/lowqualitypdf/发光材料.pdf"
        got = pdf_fetch.iri_to_uri(url)
        self.assertTrue(got.isascii())
        self.assertTrue(got.endswith("/lowqualitypdf/%E5%8F%91%E5%85%89%E6%9D%90%E6%96%99.pdf"))
        pdf_fetch._require_public_https(got)                        # accepted now

    def test_an_already_escaped_link_is_not_escaped_twice(self):
        url = "https://mkmedpress.com/uploads/L%25Vv%24mQ.pdf?a=1&b=%E5%8F%91"
        self.assertEqual(pdf_fetch.iri_to_uri(url), url)

    def test_an_international_host_is_sent_in_its_ascii_form(self):
        self.assertTrue(pdf_fetch.iri_to_uri("https://例子.中国/a.pdf").startswith("https://xn--"))

    def test_fetch_and_redirects_use_the_encoded_link(self):
        seen = []

        def net(request, timeout=None, gate=None):
            seen.append(request.full_url)
            raise urllib.error.HTTPError(request.full_url, 404, "x", {}, None)
        with tempfile.TemporaryDirectory() as root, mock.patch.object(pdf_fetch, "_open", net):
            with self.assertRaises(pdf_fetch.PdfFetchError):
                pdf_fetch.Fetcher(root).fetch("https://pub.example.org/文/a.pdf", "a")
        self.assertIn("https://pub.example.org/%E6%96%87/a.pdf", seen)


class ChainTests(unittest.TestCase):
    def setUp(self):
        pdf_fetch._CHAIN_CONTEXTS.clear()
        self.addCleanup(pdf_fetch._CHAIN_CONTEXTS.clear)

    def context_with(self, decoded, issuers):
        """chain_context with fake certificates: `decoded` maps a PEM to its fields, `issuers` an address to a PEM."""
        made = []

        class FakeContext:
            verify_flags = getattr(ssl, "VERIFY_X509_PARTIAL_CHAIN", 0x80000) | 0x8000

            def load_verify_locations(self, cadata=None):
                self.cadata = cadata
        with mock.patch.object(pdf_fetch, "_decode_cert", decoded.get), \
                mock.patch.object(pdf_fetch.ssl, "create_default_context", lambda: made.append(FakeContext()) or made[-1]):
            context = pdf_fetch.chain_context("pub.example.org", 443, fetch_server=lambda h, p: "LEAF",
                                              fetch_issuer=issuers.get)
        return context

    def test_the_missing_intermediate_is_fetched_and_added_as_a_link_never_an_anchor(self):
        context = self.context_with(
            {"LEAF": {"issuer": "R36", "subject": "pub", "caIssuers": ("http://crt.example.com/R36.crt",)},
             "R36PEM": {"issuer": "R46", "subject": "R36", "caIssuers": ("http://crt.example.com/R46.crt",)},
             "R46PEM": {"issuer": "R46", "subject": "R46"}},
            {"http://crt.example.com/R36.crt": "R36PEM", "http://crt.example.com/R46.crt": "R46PEM"})
        self.assertEqual(context.cadata, "R36PEM")                  # the self-signed root is never taken from the network
        self.assertFalse(context.verify_flags & getattr(ssl, "VERIFY_X509_PARTIAL_CHAIN", 0x80000))
        self.assertIs(pdf_fetch._CHAIN_CONTEXTS[("pub.example.org", 443)], context)

    def test_a_self_signed_certificate_offered_as_issuer_gives_no_context(self):
        context = self.context_with({"LEAF": {"issuer": "X", "subject": "pub", "caIssuers": ("http://evil.example.com/x",)},
                                     "XPEM": {"issuer": "X", "subject": "X"}}, {"http://evil.example.com/x": "XPEM"})
        self.assertIsNone(context)

    def test_no_issuer_address_gives_no_context(self):
        self.assertIsNone(self.context_with({"LEAF": {"issuer": "X", "subject": "pub"}}, {}))

    def test_an_unreachable_server_gives_no_context(self):
        def down(host, port):
            raise OSError("down")
        self.assertIsNone(pdf_fetch.chain_context("pub.example.org", 443, fetch_server=down))


class HandlerTests(unittest.TestCase):
    def setUp(self):
        pdf_fetch._CHAIN_CONTEXTS.clear()
        self.addCleanup(pdf_fetch._CHAIN_CONTEXTS.clear)

    def test_a_missing_issuer_is_retried_once_with_the_chain_of_the_real_host_behind_a_proxy(self):
        handler, calls, asked = pdf_fetch._ChainHandler(), [], []

        def do_open(connection, req, context=None):
            calls.append(context)
            if len(calls) == 1:
                raise issuer_missing()
            return "response"
        request = urllib.request.Request("https://www.example.org/robots.txt")
        request.set_proxy("127.0.0.1:10809", "http")                 # the proxy's tunnel: req.host is the proxy
        request._tunnel_host = "www.example.org"
        with mock.patch.object(handler, "do_open", do_open), \
                mock.patch.object(pdf_fetch, "chain_context", lambda h, p: asked.append((h, p)) or "CTX"):
            self.assertEqual(handler.https_open(request), "response")
        self.assertEqual((calls, asked), ([None, "CTX"], [("www.example.org", 443)]))

    def test_other_certificate_problems_are_not_retried(self):
        handler = pdf_fetch._ChainHandler()
        reason = ssl.SSLCertVerificationError(1, "certificate has expired")
        reason.verify_code = 10

        def do_open(connection, req, context=None):
            raise urllib.error.URLError(reason)
        with mock.patch.object(handler, "do_open", do_open), \
                mock.patch.object(pdf_fetch, "chain_context", side_effect=AssertionError("not asked")):
            with self.assertRaises(urllib.error.URLError):
                handler.https_open(urllib.request.Request("https://www.example.org/a.pdf"))


class ClassificationTests(unittest.TestCase):
    def test_a_certificate_failure_is_a_certificate_error_not_a_network_error(self):
        def net(request, timeout=None, gate=None):
            raise issuer_missing()
        with tempfile.TemporaryDirectory() as root, mock.patch.object(pdf_fetch, "_open", net):
            with self.assertRaises(pdf_fetch.PdfFetchError) as caught:
                pdf_fetch.Fetcher(root).fetch("https://pub.example.org/a.pdf", "a")
        self.assertEqual(caught.exception.kind, "certificate_error")

    def test_a_certificate_failure_on_the_pdf_itself_is_not_retried(self):
        calls = []

        def net(request, timeout=None, gate=None):
            calls.append(request.full_url)
            if request.full_url.endswith("/robots.txt"):
                raise urllib.error.HTTPError(request.full_url, 404, "x", {}, None)
            raise issuer_missing()
        with tempfile.TemporaryDirectory() as root, mock.patch.object(pdf_fetch, "_open", net), \
                mock.patch.object(pdf_fetch.time, "sleep", lambda s: None):
            with self.assertRaises(pdf_fetch.PdfFetchError) as caught:
                pdf_fetch.Fetcher(root).fetch("https://pub.example.org/a.pdf", "a")
        self.assertEqual((caught.exception.kind, calls.count("https://pub.example.org/a.pdf")), ("certificate_error", 1))

    def test_a_robots_txt_moved_to_plain_http_counts_as_none_and_the_pdf_is_tried(self):
        def net(request, timeout=None, gate=None):
            if request.full_url.endswith("/robots.txt"):
                pdf_fetch._require_public_https("http://elsewhere.example.org/robots.txt")   # what the redirect hop does
            raise urllib.error.HTTPError(request.full_url, 404, "x", {}, None)
        with tempfile.TemporaryDirectory() as root, mock.patch.object(pdf_fetch, "_open", net):
            with self.assertRaises(pdf_fetch.PdfFetchError) as caught:
                pdf_fetch.Fetcher(root).fetch("https://pub.example.org/a.pdf", "a")
        self.assertEqual(caught.exception.kind, "not_found")         # got as far as the PDF

    def test_the_reader_has_words_for_a_certificate_error(self):
        html = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
        self.assertIn("certificate_error: '这个来源的安全证书无法核实", html)


if __name__ == "__main__":
    unittest.main()


class UserRequestedTests(unittest.TestCase):
    """A download the person asked for does not consult robots.txt (owner, 2026-10-26); an automated one still does."""

    def fetch(self, user_requested):
        calls, gates = [], []

        def net(request, timeout=None, gate=None):
            calls.append(request.full_url)
            gates.append(gate)
            if request.full_url.endswith("/robots.txt"):
                class Robots:
                    def read(self, n=-1):
                        return b"User-agent: *\nDisallow: /\n"

                    def __enter__(self):
                        return self

                    def __exit__(self, *a):
                        return False
                return Robots()
            raise urllib.error.HTTPError(request.full_url, 404, "x", {}, None)
        with tempfile.TemporaryDirectory() as root, mock.patch.object(pdf_fetch, "_open", net):
            fetcher = pdf_fetch.Fetcher(root)
            with self.assertRaises(pdf_fetch.PdfFetchError) as caught:
                fetcher.fetch("https://iopscience.iop.org/article/10.1088/x/pdf", "a", user_requested=user_requested)
            return caught.exception.kind, calls, gates, fetcher

    def test_the_person_s_download_skips_robots_txt_and_reaches_the_pdf(self):
        kind, calls, gates, fetcher = self.fetch(True)
        self.assertEqual(kind, "not_found")
        self.assertEqual(calls, ["https://iopscience.iop.org/article/10.1088/x/pdf"])
        paced = []
        with mock.patch.object(fetcher, "_pace", paced.append), \
                mock.patch.object(fetcher, "_robots_allow", side_effect=AssertionError("robots consulted")):
            gates[-1]("https://cdn.iop.org/x.pdf")                      # a redirect hop: paced, robots not consulted
        self.assertEqual(paced, ["cdn.iop.org"])

    def test_an_automated_fetch_still_obeys_robots_txt(self):
        kind, calls, _, _ = self.fetch(False)
        self.assertEqual((kind, calls), ("robots_disallowed", ["https://iopscience.iop.org/robots.txt"]))

    def test_the_reader_s_download_is_marked_as_the_person_s_and_failures_are_logged(self):
        source = (ROOT / "app" / "service.py").read_text(encoding="utf-8")
        body = source[source.index("    def download_pdf("):source.index("    def _openalex_facts(")]
        self.assertIn("fetch(candidate[\"url\"], pdf_fetch.stem_of(paper), user_requested=True)", body)
        self.assertIn('print(f"PDF download failed: ', body)
        self.assertNotIn("title", body[body.index("PDF download failed"):body.index("continue", body.index("PDF download failed"))])

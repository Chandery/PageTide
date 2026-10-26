"""A PDF comment counts as whitespace: iText writes one between a trailer's >> and startxref, and a valid Springer PDF
downloaded in the browser was refused as "PDF 缺少索引字典结束信息" when attached (2026-10-26)."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from app.pdf_validation import validate_pdf  # noqa: E402
from pdf_fixture import minimal_pdf  # noqa: E402


class CommentTests(unittest.TestCase):
    def test_a_comment_between_the_trailer_and_startxref_is_accepted(self):
        pdf = minimal_pdf("x").replace(b">>\nstartxref", b">>\n%8f907-72fea-1a62e-a049f-5.5.13.4\nstartxref")
        self.assertTrue(validate_pdf(pdf))

    def test_several_comments_and_crlf_are_accepted(self):
        pdf = minimal_pdf("x").replace(b">>\nstartxref", b">>\r\n% one\r\n%two\r\n startxref")
        self.assertTrue(validate_pdf(pdf))

    def test_a_truncated_trailer_is_still_refused(self):
        pdf = minimal_pdf("x").replace(b"/Root 1 0 R >>\nstartxref", b"/Root 1 0 R\nstartxref")
        with self.assertRaises(ValueError):
            validate_pdf(pdf)


if __name__ == "__main__":
    unittest.main()

"""Reading the export files of a reference manager (BibTeX, RIS, CSL-JSON) with the standard library only.

The samples follow what Zotero writes, including the awkward parts: tab-indented fields, nested braces, LaTeX accents,
several attachments in one `file` field with escaped colons, and entries with no attachment at all. Hostile or huge
input must not hang or crash the importer: a broken entry is reported and skipped, the rest is kept."""
import json
import sys
import time
import unittest
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import reference_files as R

BIB = r'''
@article{vaswani_attention_2017,
	title = {Attention is all you need},
	author = {Vaswani, Ashish and Shazeer, Noam and {Google Brain}},
	date = {2017-06},
	journaltitle = {Advances in Neural Information Processing Systems},
	doi = {10.5555/3295222.3295349},
	abstract = {The dominant sequence transduction models are based on complex recurrent or convolutional neural networks.},
	file = {Full Text PDF:files/12/Vaswani et al. - 2017 - Attention is all you need.pdf:application/pdf;Snapshot:files/13/index.html:text/html},
}

@inproceedings{devlin_bert_2019,
	title = {{BERT}: {Pre}-training of {Deep} {Bidirectional} {Transformers}},
	author = {Devlin, Jacob and Chang, Ming-Wei},
	year = {2019},
	booktitle = {NAACL},
	url = {https://arxiv.org/abs/1810.04805},
	eprint = {1810.04805},
	eprinttype = {arxiv},
	file = {PDF:files/20/Devlin.pdf:application/pdf},
}

@book{scholkopf_learning_2002,
	title = "Learning with {K}ernels: Support Vector Machines \& Beyond",
	author = {Sch{\"o}lkopf, Bernhard and Smola, Alex J.},
	year = 2002,
	publisher = {MIT Press},
}

@misc{no_file_2020,
	title = {A reference without any attachment},
	author = {Nobody, N.},
	date = {2020},
	file = {},
}

@comment{this is not an entry}
@string{nips = "Neural Information Processing Systems"}

@article{colon_2021,
	title = {Paths with \: colons \; and semicolons},
	author = {Author, A.},
	year = {2021},
	file = {Full Text:files/30/a\: b\; c.pdf:application/pdf},
}
'''

RIS = '''TY  - JOUR
TI  - Attention is all you need
AU  - Vaswani, Ashish
AU  - Shazeer, Noam
PY  - 2017///
DO  - 10.5555/3295222.3295349
AB  - The dominant sequence transduction models.
JO  - NeurIPS
L1  - files/12/Vaswani et al. - 2017.pdf
L1  - files/13/snapshot.html
ER  -

TY  - JOUR
T1  - Second paper, no attachment
A1  - Someone, S.
Y1  - 2020/05/01
UR  - https://arxiv.org/abs/2005.00001
ER  -

TY  - JOUR
ER  -
'''

CSL = json.dumps([
    {"id": "a1", "type": "article-journal", "title": "Attention is all you need", "DOI": "10.5555/3295222.3295349",
     "author": [{"family": "Vaswani", "given": "Ashish"}, {"literal": "Google Brain"}], "issued": {"date-parts": [[2017, 6]]},
     "container-title": "NeurIPS", "abstract": "Abstract text."},
    {"id": "a2", "type": "article", "title": "A preprint", "URL": "https://arxiv.org/abs/2401.00001"},
    {"id": "a3", "type": "article"},
    "not an object",
])


class BibTeXTests(unittest.TestCase):
    def setUp(self):
        out = R.parse_bibtex(BIB)
        self.entries = {e["id"]: e for e in out["entries"]}
        self.errors = out["errors"]

    def test_every_real_entry_is_read_and_comments_and_macros_are_skipped(self):
        self.assertEqual(sorted(self.entries), ["colon_2021", "devlin_bert_2019", "no_file_2020", "scholkopf_learning_2002", "vaswani_attention_2017"])

    def test_the_common_fields_are_normalised(self):
        e = self.entries["vaswani_attention_2017"]
        self.assertEqual(e["title"], "Attention is all you need")
        self.assertEqual(e["authors"], ["Vaswani, Ashish", "Shazeer, Noam", "Google Brain"])
        self.assertEqual((e["year"], e["doi"], e["venue"]), (2017, "10.5555/3295222.3295349", "Advances in Neural Information Processing Systems"))
        self.assertTrue(e["abstract"].startswith("The dominant sequence"))

    def test_braces_that_protect_capitals_are_removed_and_year_may_be_a_bare_number(self):
        self.assertEqual(self.entries["devlin_bert_2019"]["title"], "BERT: Pre-training of Deep Bidirectional Transformers")
        self.assertEqual(self.entries["scholkopf_learning_2002"]["year"], 2002)

    def test_latex_accents_and_escapes_become_text_and_quoted_values_work(self):
        e = self.entries["scholkopf_learning_2002"]
        self.assertEqual(e["authors"][0], "Schölkopf, Bernhard")
        self.assertEqual(e["title"], "Learning with Kernels: Support Vector Machines & Beyond")

    def test_an_arxiv_id_comes_from_eprint_or_the_url(self):
        self.assertEqual(self.entries["devlin_bert_2019"]["arxiv"], "1810.04805")
        self.assertIsNone(self.entries["vaswani_attention_2017"]["arxiv"])

    def test_only_pdf_attachments_are_kept_with_their_relative_paths(self):
        self.assertEqual(self.entries["vaswani_attention_2017"]["files"], ["files/12/Vaswani et al. - 2017 - Attention is all you need.pdf"])
        self.assertEqual(self.entries["devlin_bert_2019"]["files"], ["files/20/Devlin.pdf"])
        self.assertEqual(self.entries["no_file_2020"]["files"], [])
        self.assertEqual(self.entries["scholkopf_learning_2002"]["files"], [])

    def test_escaped_colons_and_semicolons_in_a_path_survive(self):
        self.assertEqual(self.entries["colon_2021"]["files"], ["files/30/a: b; c.pdf"])
        self.assertEqual(self.entries["colon_2021"]["title"], "Paths with : colons ; and semicolons")

    def test_a_broken_entry_is_reported_and_the_others_survive(self):
        out = R.parse_bibtex("@article{ok1,\n title = {Fine},\n}\n@article{broken,\n title = {Never closed\n")
        self.assertEqual([e["id"] for e in out["entries"]], ["ok1"])
        self.assertTrue(out["errors"])

    def test_an_entry_without_a_title_is_dropped_with_a_reason(self):
        out = R.parse_bibtex("@article{x,\n author = {A, B},\n year = {2020},\n}\n")
        self.assertEqual(out["entries"], [])
        self.assertIn("x", out["errors"][0])

    def test_hostile_nesting_and_size_do_not_hang(self):
        deep = "@article{x,\n title = {" + "{" * 5000 + "a" + "}" * 5000 + "},\n}\n"
        out = R.parse_bibtex(deep)
        self.assertLessEqual(len(out["entries"]) + len(out["errors"]), 1)
        out = R.parse_bibtex("@article{k,\n title = {t},\n" + "x = {y},\n" * 50000 + "}\n")
        self.assertEqual(len(out["entries"]), 1)


class RisTests(unittest.TestCase):
    def test_entries_fields_and_attachments(self):
        out = R.parse_ris(RIS)
        first, second = out["entries"]
        self.assertEqual((first["title"], first["authors"], first["year"], first["doi"], first["venue"]),
                         ("Attention is all you need", ["Vaswani, Ashish", "Shazeer, Noam"], 2017, "10.5555/3295222.3295349", "NeurIPS"))
        self.assertEqual(first["files"], ["files/12/Vaswani et al. - 2017.pdf"])
        self.assertEqual((second["title"], second["year"], second["arxiv"], second["files"]), ("Second paper, no attachment", 2020, "2005.00001", []))

    def test_a_record_without_a_title_is_reported(self):
        out = R.parse_ris(RIS)
        self.assertEqual(len(out["entries"]), 2)
        self.assertEqual(len(out["errors"]), 1)

    def test_byte_order_mark_and_windows_line_endings(self):
        out = R.parse_ris("﻿" + RIS.replace("\n", "\r\n"))
        self.assertEqual(len(out["entries"]), 2)


class CslTests(unittest.TestCase):
    def test_items_are_read_and_junk_is_reported(self):
        out = R.parse_csl_json(CSL)
        first, second = out["entries"]
        self.assertEqual((first["title"], first["authors"], first["year"], first["doi"]),
                         ("Attention is all you need", ["Vaswani, Ashish", "Google Brain"], 2017, "10.5555/3295222.3295349"))
        self.assertEqual((first["venue"], first["files"]), ("NeurIPS", []))
        self.assertEqual(second["arxiv"], "2401.00001")
        self.assertEqual(len(out["errors"]), 2)   # the item with no title and the one that is not an object

    def test_not_json_or_not_a_list_is_an_error_not_a_crash(self):
        for bad in ("nope", "{}", "42", ""):
            out = R.parse_csl_json(bad)
            self.assertEqual(out["entries"], [])
            self.assertTrue(out["errors"])


class HostileInputTests(unittest.TestCase):
    """Reviewer-found shapes that were slow or raised something the importer does not catch."""

    def timed(self, work, seconds=3.0):
        started = time.monotonic()
        result = work()
        self.assertLess(time.monotonic() - started, seconds)
        return result

    def test_an_accent_followed_by_a_long_run_of_spaces_is_linear(self):
        for text in ("\\'" + " " * 100000 + "1", "\\c" + " " * 100000 + "1", "\\'{" + " " * 100000 + "1"):
            self.timed(lambda: R.latex(text))

    def test_a_ris_value_wrapped_over_very_many_lines_is_linear(self):
        text = "TY  - JOUR\nTI  - Title\nAB  - start\n" + "x\n" * 300000 + "ER  - \n"
        out = self.timed(lambda: R.parse_ris(text))
        self.assertEqual(out["entries"][0]["title"], "Title")
        self.assertLessEqual(len(out["entries"][0]["abstract"]), R.MAX_ABSTRACT)

    def test_csl_json_of_any_shape_is_an_error_or_an_entry_never_an_exception(self):
        for text in ("[" * 100000, '[{"title": "x", "issued": {"date-parts": [2020]}}]', '[{"title": "x", "author": 5}]',
                     '[{"title": "x", "author": [5, null, {"family": 3}]}]', '[{"title": "x", "issued": 7}]',
                     '[{"title": ["a", "b"]}]', '[{"title": "x", "DOI": 5, "URL": ["u"]}]', '[{"title": "x", "container-title": 5}]'):
            out = self.timed(lambda: R.parse_csl_json(text))
            self.assertIsInstance(out["entries"], list, text[:40])
            self.assertIsInstance(out["errors"], list, text[:40])

    def test_csl_year_authors_and_venue_survive_odd_but_valid_shapes(self):
        out = R.parse_csl_json(json.dumps([{"title": "x", "issued": {"date-parts": [[2020, 5]]}, "container-title": ["Nature", "Nat."],
                                            "author": [{"family": "A", "given": "B"}]},
                                           {"title": "y", "issued": {"date-parts": [["2019"]]}},
                                           {"title": "z", "issued": {"raw": "2018-03-04"}}]))
        years = [e["year"] for e in out["entries"]]
        self.assertEqual(years, [2020, 2019, 2018])
        self.assertEqual(out["entries"][0]["venue"], "Nature")

    def test_an_escaped_underscore_in_a_bibtex_doi_does_not_make_a_second_key(self):
        out = R.parse_bibtex("@article{k,\n title = {T},\n doi = {10.1000/ab\\_c},\n}\n")
        self.assertEqual(out["entries"][0]["doi"], "10.1000/ab_c")

    def test_the_module_compiles_without_escape_warnings(self):
        source = (ROOT / "app" / "reference_files.py").read_text(encoding="utf-8")
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            compile(source, "reference_files.py", "exec")


class DispatchTests(unittest.TestCase):
    def test_the_format_picks_the_parser_and_bytes_are_decoded(self):
        self.assertEqual(len(R.parse("bibtex", BIB.encode("utf-8"))["entries"]), 5)
        self.assertEqual(len(R.parse("ris", RIS.encode("utf-8-sig"))["entries"]), 2)
        self.assertEqual(len(R.parse("csljson", CSL.encode("utf-8"))["entries"]), 2)

    def test_unknown_format_oversize_and_bad_bytes_are_refused_or_survived(self):
        with self.assertRaises(ValueError):
            R.parse("endnote", b"x")
        with self.assertRaises(ValueError):
            R.parse("bibtex", b"x" * (R.MAX_BYTES + 1))
        self.assertEqual(len(R.parse("bibtex", BIB.encode("latin-1", "replace"))["entries"]), 5)

    def test_the_number_of_entries_is_capped(self):
        many = "".join(f"@article{{k{i},\n title = {{Title {i}}},\n}}\n" for i in range(R.MAX_ENTRIES + 10))
        out = R.parse_bibtex(many)
        self.assertEqual(len(out["entries"]), R.MAX_ENTRIES)
        self.assertTrue(any("上限" in e or "limit" in e.lower() for e in out["errors"]))

    def test_format_names_follow_the_file_extension(self):
        for name, fmt in (("My Library.bib", "bibtex"), ("x.BIBTEX", "bibtex"), ("export.ris", "ris"), ("items.json", "csljson"), ("a.csljson", "csljson")):
            self.assertEqual(R.format_of(name), fmt, name)
        self.assertIsNone(R.format_of("notes.txt"))


if __name__ == "__main__":
    unittest.main()

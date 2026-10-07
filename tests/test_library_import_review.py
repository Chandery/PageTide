"""Review actions on one item: choose a candidate, look it up by hand, keep it as a plain PDF, exclude it.

Every action is the person's own decision, so nothing here is automatic and nothing is a model call."""
import io
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.db import Store
from app.library_import import LibraryImport
from app.project import ProjectManager
from app.sources import SourceError
from tests.library_import_fixtures import FakeClient, pdf, work


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data = Path(self.tmp.name)
        self.store = Store(self.data / "paperdighelper.sqlite")
        self.store.init()
        self.project = ProjectManager(self.store).create_project("导入测试")
        self.client = FakeClient()
        self.imp = LibraryImport(self.data, self.store, self.client)
        self.batch_id = self.imp.create_batch(self.project, "folder", "r", {})["id"]
        self.n = 0

    def add(self, hints=None, name=None):
        self.n += 1
        data = pdf(self.n)
        return self.imp.add_pdf(self.batch_id, f"r/{name or f'f{self.n}.pdf'}", io.BytesIO(data), len(data), 1, hints)

    def act(self, item, action, **kw):
        return self.imp.act(self.batch_id, item["id"], action, **kw)

    def undecided(self):
        item = self.add({"titles": ["Neural world models"]})
        candidates = [{"paper": {"key": "https://doi.org/10.1000/c1", "title": "World models in practice", "doi": "https://doi.org/10.1000/c1"},
                       "score": 0.4, "existing": False},
                      {"paper": {"key": "k-existing", "title": "Neural world models"}, "score": 1.0, "existing": True}]
        self.imp._set(item["id"], "needs_choice", match_source="title", candidates=candidates)
        return item


class ChooseTests(Base):
    def test_picking_a_candidate_matches_the_item_to_it(self):
        item = self.undecided()
        got = self.act(item, "pick", index=0)
        self.assertEqual((got["state"], got["match_source"]), ("matched", "user_pick"))
        self.assertEqual(got["paper"]["key"], "https://doi.org/10.1000/c1")

    def test_picking_a_paper_already_in_the_library_links_to_it(self):
        item = self.undecided()
        got = self.act(item, "pick", index=1)
        self.assertEqual((got["state"], got["match_source"], got["paper_key"]), ("duplicate", "existing", "k-existing"))

    def test_a_candidate_that_does_not_exist_is_refused(self):
        item = self.undecided()
        for bad in (5, -1, "x", None):
            with self.assertRaises(ValueError, msg=bad):
                self.act(item, "pick", index=bad)
        self.assertEqual(self.imp.item(self.batch_id, item["id"])["state"], "needs_choice")

    def test_keeping_it_as_a_plain_pdf_uses_the_title_found_in_the_file_or_its_name(self):
        item = self.undecided()
        got = self.act(item, "unresolved")
        self.assertEqual((got["state"], got["match_source"]), ("unmatched", "unresolved"))
        self.assertEqual(got["paper"], {"key": "pdf:" + item["sha256"], "title": "Neural world models", "unresolved": True})
        plain = self.add(None, name="notes from 2019.pdf")
        self.imp._set(plain["id"], "failed", error="x")
        self.assertEqual(self.act(plain, "unresolved")["paper"]["title"], "notes from 2019")


class LookupTests(Base):
    def test_a_typed_doi_is_looked_up_and_matched(self):
        item = self.add()
        self.imp._set(item["id"], "unmatched", match_source="unresolved", paper={"key": "pdf:x", "title": "t", "unresolved": True})
        self.client.works["https://doi.org/10.1000/p9"] = work(9)
        got = self.act(item, "lookup", text="doi:10.1000/p9")
        self.assertEqual((got["state"], got["match_source"], got["paper"]["openalex_id"]), ("matched", "user_lookup", "https://openalex.org/W9"))

    def test_a_typed_name_offers_candidates_to_choose_from(self):
        item = self.add()
        self.imp._set(item["id"], "unmatched", match_source="unresolved", paper={"key": "pdf:x", "title": "t", "unresolved": True})
        self.client.titles["Attention is all you need"] = [work(1, "Attention Is All You Need"), work(2, "Attention in vision"), work(3, "Cooking")]
        got = self.act(item, "lookup", text="Attention is all you need")
        self.assertEqual(got["state"], "needs_choice")
        self.assertEqual([c["paper"]["openalex_id"][-2:] for c in got["candidates"]], ["W1", "W2"])

    def test_a_lookup_the_person_types_is_their_own_query_even_with_online_matching_off(self):
        # Online matching off means the import never goes online by itself. A lookup typed on the confirm step is the
        # person's own action, and the page says so; this pins that behaviour so the wording and the code stay together.
        offline = self.imp.create_batch(self.project, "folder", "r", {"online": False})["id"]
        data = pdf(77)
        item = self.imp.add_pdf(offline, "r/a.pdf", io.BytesIO(data), len(data), 1, None)
        self.client.titles["Attention is all you need"] = [work(1, "Attention Is All You Need")]
        got = self.imp.act(offline, item["id"], "lookup", text="Attention is all you need")
        self.assertEqual(got["state"], "needs_choice")
        self.assertEqual(self.client.calls, [("title", "Attention is all you need")])

    def test_nothing_found_says_so_and_leaves_the_item_as_it_was(self):
        item = self.undecided()
        before = self.imp.item(self.batch_id, item["id"])
        with self.assertRaises(ValueError):
            self.act(item, "lookup", text="a title nobody ever wrote")
        with self.assertRaises(ValueError):
            self.act(item, "lookup", text="10.1000/missing")
        self.assertEqual(self.imp.item(self.batch_id, item["id"]), before)

    def test_a_service_that_cannot_answer_gives_a_reason_not_a_crash(self):
        item = self.undecided()
        for kind, word in (("unavailable", "限流"), ("network_error", "网络")):
            self.client.fail = ("title", SourceError("x", kind))
            with self.assertRaises(ValueError) as caught:
                self.act(item, "lookup", text="Neural world models")
            self.assertIn(word, str(caught.exception))
        self.assertEqual(self.imp.item(self.batch_id, item["id"])["state"], "needs_choice")

    def test_too_short_or_empty_text_is_refused_before_any_request(self):
        item = self.undecided()
        for text in ("", "  ", "ab", None, "x" * 400):
            with self.assertRaises(ValueError, msg=text):
                self.act(item, "lookup", text=text)
        self.assertEqual(self.client.calls, [])


class ExcludeTests(Base):
    def test_excluding_then_including_restores_what_the_item_was(self):
        for state, fields in (("matched", {"paper": {"key": "a", "title": "t"}, "match_source": "title"}),
                              ("unmatched", {"paper": {"key": "pdf:x", "title": "t", "unresolved": True}, "match_source": "unresolved"}),
                              ("duplicate", {"paper": {"key": "k", "title": "t"}, "paper_key": "k", "match_source": "existing"}),
                              ("needs_choice", {"candidates": [{"paper": {"key": "c", "title": "t"}, "score": .5, "existing": False}]})):
            item = self.add()
            self.imp._set(item["id"], state, **fields)
            self.assertEqual(self.act(item, "exclude")["state"], "excluded")
            self.assertEqual(self.act(item, "include")["state"], state, state)

    def test_an_item_with_no_outcome_goes_back_to_pending_when_included(self):
        item = self.add()
        self.imp._set(item["id"], "excluded")
        self.assertEqual(self.act(item, "include")["state"], "pending")


class GuardTests(Base):
    def test_unknown_actions_and_closed_batches_are_refused(self):
        item = self.undecided()
        with self.assertRaises(ValueError):
            self.act(item, "explode")
        self.imp.discard(self.batch_id)
        with self.assertRaises(ValueError):
            self.act(item, "exclude")

    def test_an_item_from_another_batch_is_not_reachable(self):
        item = self.undecided()
        other = self.imp.create_batch(self.project, "files", "", {})["id"]
        with self.assertRaises(ValueError):
            self.imp.act(other, item["id"], "exclude")

    def test_a_committed_item_cannot_be_changed(self):
        item = self.add()
        self.imp._set(item["id"], "matched", paper={"key": "https://doi.org/10.1000/p1", "title": "t"}, match_source="title")
        self.imp.commit(self.batch_id)
        with self.assertRaises(ValueError):
            self.act(item, "exclude")


if __name__ == "__main__":
    unittest.main()

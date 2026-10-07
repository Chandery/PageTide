"""Matching staged PDFs to public metadata: identifiers first, titles second, quota-aware, offline-capable.

A fake client stands in for OpenAlex, so no test touches the network. The client's own pacing and cache are
tested elsewhere; here we pin what the importer asks for, how it decides, and when it stops instead of failing."""
import io
import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import library_import
from app.db import Store
from app.library_import import LibraryImport
from app.project import ProjectManager
from app.sources import SourceError, similarity
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
        self.n = 0

    def batch(self, **options):
        self.batch_id = self.imp.create_batch(self.project, "folder", "r", options)["id"]
        return self.batch_id

    def add(self, hints=None, name=None, data=None):
        self.n += 1
        data = data or pdf(self.n)
        return self.imp.add_pdf(self.batch_id, f"r/{name or f'f{self.n}.pdf'}", io.BytesIO(data), len(data), 1, hints)

    def state(self, item):
        return self.imp.item(self.batch_id, item["id"])


class SimilarityTests(unittest.TestCase):
    def test_matches_the_page_script(self):
        self.assertEqual(similarity("Attention Is All You Need", "attention is all you need!"), 1.0)
        self.assertAlmostEqual(similarity("a b c d", "a b x y"), 1 / 3)
        self.assertEqual(similarity("", "x"), 0)
        self.assertEqual(similarity("世界模型 综述", "世界模型综述"), 0)  # whole-run CJK token, like the script


class IdentifierMatchTests(Base):
    def test_a_doi_is_looked_up_in_one_batched_request_and_matches(self):
        self.batch()
        item = self.add({"doi": "10.1000/P1"})
        self.client.dois["https://doi.org/10.1000/p1"] = work(1)
        self.assertEqual(self.imp.resolve(self.batch_id), "review")
        got = self.state(item)
        self.assertEqual((got["state"], got["match_source"]), ("matched", "pdf_id"))
        self.assertEqual(got["paper"]["key"], "https://doi.org/10.1000/p1")
        self.assertEqual(self.client.names(), ["dois"])
        self.assertEqual(self.client.calls[0][1], ["https://doi.org/10.1000/p1"])

    def test_many_dois_go_in_chunks_of_fifty(self):
        self.batch()
        for i in range(120):
            self.add({"doi": f"10.1000/q{i}"})
        self.imp.resolve(self.batch_id)
        sizes = [len(c[1]) for c in self.client.calls if c[0] == "dois"]
        self.assertEqual(sizes, [50, 50, 20])

    def test_a_doi_that_could_change_the_filter_is_fetched_alone(self):
        self.batch()
        self.add({"doi": "10.1000/a,b"})
        self.add({"doi": "10.1000/c|d"})
        self.imp.resolve(self.batch_id)
        self.assertEqual(self.client.names().count("dois"), 0)
        self.assertEqual(self.client.names().count("work"), 2)

    def test_an_arxiv_id_is_resolved_through_its_doi(self):
        self.batch()
        item = self.add({"arxiv": "2401.00001"})
        self.client.arxiv["https://doi.org/10.48550/arxiv.2401.00001"] = work(7, doi="https://doi.org/10.48550/arxiv.2401.00001")
        self.imp.resolve(self.batch_id)
        self.assertEqual(self.state(item)["state"], "matched")
        self.assertEqual(self.state(item)["paper"]["arxiv_id"], "2401.00001")

    def test_an_arxiv_id_in_the_file_name_counts(self):
        self.batch()
        item = self.add(None, name="2401.00002v2.pdf")
        self.client.arxiv["https://doi.org/10.48550/arxiv.2401.00002v2"] = work(8, doi="https://doi.org/10.48550/arxiv.2401.00002")
        self.imp.resolve(self.batch_id)
        got = self.state(item)
        self.assertEqual(got["state"], "matched")

    def test_an_unknown_identifier_falls_back_to_the_title(self):
        self.batch()
        item = self.add({"doi": "10.1000/zzz", "titles": ["Deep learning for robots"]})
        self.client.titles["Deep learning for robots"] = [work(3, "Deep learning for robots")]
        self.imp.resolve(self.batch_id)
        got = self.state(item)
        self.assertEqual((got["state"], got["match_source"]), ("matched", "title"))


class IdentifierSanityTests(Base):
    """A DOI read off the first pages may belong to a paper the PDF merely cites. The person is not there to confirm
    each of hundreds of matches, so a match whose title shares nothing with the title read from the same PDF is asked about."""

    def resolve_one(self, hints, found):
        self.batch()
        item = self.add(hints)
        self.client.dois["https://doi.org/10.1000/p1"] = found
        self.imp.resolve(self.batch_id)
        return self.state(item)

    def test_an_identifier_whose_paper_has_an_unrelated_title_is_not_accepted_silently(self):
        got = self.resolve_one({"doi": "10.1000/p1", "titles": ["A study of learning latent dynamics for robots"]},
                               work(1, "Crystal growth of ionic salts under pressure"))
        self.assertEqual((got["state"], got["match_source"]), ("needs_choice", "pdf_id"))
        self.assertEqual(got["candidates"][0]["paper"]["title"], "Crystal growth of ionic salts under pressure")
        self.assertLess(got["candidates"][0]["score"], 0.25)
        self.assertEqual(self.imp.act(self.batch_id, got["id"], "pick", index=0)["state"], "matched")

    def test_an_identifier_whose_paper_agrees_with_the_pdfs_own_title_is_accepted(self):
        got = self.resolve_one({"doi": "10.1000/p1", "titles": ["Learning latent dynamics for robots"]},
                               work(1, "Learning Latent Dynamics for Robots"))
        self.assertEqual((got["state"], got["match_source"]), ("matched", "pdf_id"))

    def test_with_no_title_read_from_the_pdf_there_is_nothing_to_compare_and_it_is_accepted(self):
        self.assertEqual(self.resolve_one({"doi": "10.1000/p1"}, work(1, "Anything at all"))["state"], "matched")

    def test_titles_too_short_to_compare_do_not_trigger_the_check(self):
        self.assertEqual(self.resolve_one({"doi": "10.1000/p1", "titles": ["Transformers"]}, work(1, "Attention is all you need"))["state"], "matched")

    def test_the_export_is_trusted_over_the_pdf_so_it_is_never_questioned(self):
        self.batch()
        item = self.add({"doi": "10.1000/p1", "titles": ["A study of learning latent dynamics for robots"]})
        self.imp.conn.execute("UPDATE import_items SET entry=? WHERE id=?",
                              (json.dumps({"title": "Whatever the export says", "doi": "10.1000/p1", "authors": [], "year": 2020, "files": []}), item["id"]))
        self.imp.conn.commit()
        self.client.dois["https://doi.org/10.1000/p1"] = work(1, "Crystal growth of ionic salts under pressure")
        self.imp.resolve(self.batch_id)
        self.assertEqual((self.state(item)["state"], self.state(item)["match_source"]), ("matched", "sidecar"))


class RefusedRequestTests(Base):
    """One odd identifier must not stall the import for ever: a refused request is not a dead network."""

    def test_a_refused_batch_of_dois_is_asked_again_one_at_a_time_and_only_the_bad_one_fails(self):
        self.batch()
        good, bad, other = (self.add({"doi": f"10.1000/q{i}"}) for i in range(3))
        self.client.fail = ("dois", SourceError("HTTP Error 400", "invalid_input"))
        self.client.arxiv["https://doi.org/10.1000/q0"] = work(10, doi="https://doi.org/10.1000/q0")
        self.client.arxiv["https://doi.org/10.1000/q2"] = work(12, doi="https://doi.org/10.1000/q2")
        self.client.work_errors["https://doi.org/10.1000/q1"] = SourceError("HTTP Error 400", "invalid_input")
        self.assertEqual(self.imp.resolve(self.batch_id), "review")
        self.assertEqual([self.state(i)["state"] for i in (good, bad, other)], ["matched", "failed", "matched"])
        self.assertEqual(self.client.names().count("dois"), 1)    # asked as a batch once, never repeated

    def test_one_doi_alone_that_is_refused_just_fails(self):
        self.batch()
        item = self.add({"doi": "10.1000/q1"})
        self.client.fail = ("dois", SourceError("HTTP Error 400", "invalid_input"))
        self.assertEqual(self.imp.resolve(self.batch_id), "review")
        self.assertEqual(self.state(item)["state"], "failed")
        self.assertEqual(self.client.names(), ["dois"])

    def test_a_dead_network_while_asking_one_at_a_time_still_pauses(self):
        self.batch()
        first, second = self.add({"doi": "10.1000/q0"}), self.add({"doi": "10.1000/q1"})
        self.client.fail = ("dois", SourceError("HTTP Error 400", "invalid_input"))
        self.client.work_errors["https://doi.org/10.1000/q0"] = SourceError("down", "network_error")
        self.assertEqual(self.imp.resolve(self.batch_id), "paused")
        self.assertEqual(self.imp.batch(self.batch_id)["pause_reason"], "network")
        self.assertEqual([self.state(i)["state"] for i in (first, second)], ["pending", "pending"])


class TitleMatchTests(Base):
    def test_a_close_title_is_accepted_without_asking(self):
        self.batch()
        item = self.add({"titles": ["Attention is all you need"]})
        self.client.titles["Attention is all you need"] = [work(1, "Something else entirely"), work(2, "Attention Is All You Need")]
        self.imp.resolve(self.batch_id)
        got = self.state(item)
        self.assertEqual((got["state"], got["paper"]["openalex_id"]), ("matched", "https://openalex.org/W2"))

    def test_two_equally_good_hits_are_not_decided_for_the_person(self):
        # a preprint and its journal version carry the same title
        self.batch()
        item = self.add({"titles": ["Attention is all you need"]})
        self.client.titles["Attention is all you need"] = [work(1, "Attention Is All You Need"), work(2, "Attention is all you need")]
        self.imp.resolve(self.batch_id)
        got = self.state(item)
        self.assertEqual(got["state"], "needs_choice")
        self.assertEqual(len(got["candidates"]), 2)

    def test_a_clear_winner_is_still_accepted(self):
        self.batch()
        item = self.add({"titles": ["Attention is all you need"]})
        self.client.titles["Attention is all you need"] = [work(1, "Attention Is All You Need"), work(2, "Attention is all you need today")]
        self.imp.resolve(self.batch_id)
        self.assertEqual(self.state(item)["state"], "matched")
        self.assertEqual(self.state(item)["paper"]["openalex_id"], "https://openalex.org/W1")

    def test_a_one_word_title_is_never_accepted_on_its_own(self):
        self.batch()
        item = self.add({"titles": ["Transformers"]})
        self.client.titles["Transformers"] = [work(1, "Transformers")]
        self.imp.resolve(self.batch_id)
        self.assertEqual(self.state(item)["state"], "needs_choice")

    def test_a_weak_title_match_asks_the_person_and_offers_at_most_five(self):
        self.batch()
        item = self.add({"titles": ["Neural world models"]})
        self.client.titles["Neural world models"] = [work(i, f"World models in practice {i}") for i in range(1, 9)]
        self.imp.resolve(self.batch_id)
        got = self.state(item)
        self.assertEqual(got["state"], "needs_choice")
        self.assertEqual(len(got["candidates"]), 5)
        scores = [c["score"] for c in got["candidates"]]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_hits_that_share_nothing_are_not_offered(self):
        self.batch()
        item = self.add({"titles": ["Neural world models"]})
        self.client.titles["Neural world models"] = [work(1, "Cooking pasta at home")]
        self.imp.resolve(self.batch_id)
        self.assertEqual(self.state(item)["state"], "unmatched")

    def test_no_hint_at_all_is_unmatched_without_any_request(self):
        self.batch()
        item = self.add(None, name="scan 0042.pdf")
        self.imp.resolve(self.batch_id)
        got = self.state(item)
        self.assertEqual((got["state"], got["match_source"]), ("unmatched", "unresolved"))
        self.assertEqual(self.client.calls, [])


class OfflineAndExistingTests(Base):
    def test_with_online_lookup_off_nothing_leaves_the_machine(self):
        self.batch(online=False)
        a = self.add({"doi": "10.1000/p1", "titles": ["A title that is long enough"]})
        self.imp.resolve(self.batch_id)
        self.assertEqual(self.client.calls, [])
        self.assertEqual(self.state(a)["state"], "unmatched")
        self.assertEqual(self.imp.batch(self.batch_id)["status"], "review")

    def test_a_paper_already_in_the_database_is_linked_not_looked_up(self):
        self.store.upsert_papers([{"key": "https://doi.org/10.1000/p1", "title": "Known", "doi": "https://doi.org/10.1000/p1"}],
                                 project_id=self.project)
        self.batch()
        item = self.add({"doi": "10.1000/P1"})
        self.imp.resolve(self.batch_id)
        got = self.state(item)
        self.assertEqual((got["state"], got["match_source"], got["paper_key"]), ("duplicate", "existing", "https://doi.org/10.1000/p1"))
        self.assertEqual(self.client.calls, [])

    def test_a_file_already_archived_for_a_paper_is_linked_to_it(self):
        self.batch()
        data = pdf(99)
        item = self.add({"titles": ["Some long enough title"]}, data=data)
        self.store.upsert_papers([{"key": "k1", "title": "Archived paper"}], project_id=self.project)
        self.store.record_pdf("k1", "/x/a.pdf", "user-import", sha256=item["sha256"], size=len(data))
        self.imp.resolve(self.batch_id)
        got = self.state(item)
        self.assertEqual((got["state"], got["paper_key"]), ("duplicate", "k1"))
        self.assertEqual(self.client.calls, [])

    def test_an_identical_title_in_the_library_asks_instead_of_adding_a_twin(self):
        self.store.upsert_papers([{"key": "k1", "title": "Attention is all you need"}], project_id=self.project)
        self.batch()
        item = self.add({"titles": ["Attention Is All You Need"]})
        self.imp.resolve(self.batch_id)
        got = self.state(item)
        self.assertEqual(got["state"], "needs_choice")
        self.assertEqual(got["candidates"][0]["paper"]["key"], "k1")
        self.assertTrue(got["candidates"][0]["existing"])

    def test_in_batch_copies_are_not_resolved_twice(self):
        self.batch()
        data = pdf(5)
        self.add({"doi": "10.1000/p1"}, data=data)
        self.add({"doi": "10.1000/p1"}, name="copy.pdf", data=data)
        self.imp.resolve(self.batch_id)
        self.assertEqual(self.client.calls[0][1], ["https://doi.org/10.1000/p1"])
        self.assertEqual(len(self.client.calls), 1)


class StopsGracefullyTests(Base):
    def test_low_openalex_credits_pause_the_batch_before_any_request(self):
        self.batch()
        item = self.add({"titles": ["A title that is long enough"]})
        self.client.limit = {"remaining": 5, "observed_at": time.time(), "reset_seconds": 3600}
        self.assertEqual(self.imp.resolve(self.batch_id), "paused")
        self.assertEqual(self.client.calls, [])
        self.assertEqual(self.imp.batch(self.batch_id)["pause_reason"], "openalex_quota")
        self.assertEqual(self.state(item)["state"], "pending")

    def test_an_expired_allowance_note_is_ignored(self):
        self.batch()
        self.add({"titles": ["A title that is long enough"]})
        self.client.limit = {"remaining": 0, "observed_at": time.time() - 7200, "reset_seconds": 3600}
        self.assertEqual(self.imp.resolve(self.batch_id), "review")

    def test_a_busy_service_pauses_and_keeps_what_was_done(self):
        self.batch()
        first = self.add({"titles": ["First long enough title"]})
        second = self.add({"titles": ["Second long enough title"]})
        self.client.titles["First long enough title"] = [work(1, "First long enough title")]
        self.client.fail, self.client.fail_after = ("title", SourceError("busy", "unavailable")), 1
        self.assertEqual(self.imp.resolve(self.batch_id), "paused")
        self.assertEqual(self.imp.batch(self.batch_id)["pause_reason"], "openalex_quota")
        self.assertEqual(self.state(first)["state"], "matched")
        self.assertEqual(self.state(second)["state"], "pending")
        self.client.fail = None
        self.assertEqual(self.imp.resolve(self.batch_id), "review")
        self.assertEqual(self.state(second)["state"], "unmatched")

    def test_no_network_pauses_instead_of_marking_everything_unmatched(self):
        self.batch()
        item = self.add({"titles": ["A title that is long enough"]})
        self.client.fail = ("title", SourceError("down", "network_error"))
        self.assertEqual(self.imp.resolve(self.batch_id), "paused")
        self.assertEqual(self.imp.batch(self.batch_id)["pause_reason"], "network")
        self.assertEqual(self.state(item)["state"], "pending")

    def test_a_bad_reply_fails_that_item_only(self):
        self.batch()
        bad = self.add({"titles": ["A title that is long enough"]})
        good = self.add(None, name="x.pdf")
        self.client.fail = ("title", SourceError("junk", "bad_response"))
        self.assertEqual(self.imp.resolve(self.batch_id), "review")
        self.assertEqual(self.state(bad)["state"], "failed")
        self.assertEqual(self.state(good)["state"], "unmatched")

    def test_cancelling_pauses_between_items(self):
        self.batch()
        item = self.add({"titles": ["A title that is long enough"]})
        stop = threading.Event()
        stop.set()
        self.assertEqual(self.imp.resolve(self.batch_id, cancel=stop), "paused")
        self.assertEqual(self.imp.batch(self.batch_id)["pause_reason"], "cancelled")
        self.assertEqual(self.state(item)["state"], "pending")

    def test_items_left_resolving_by_a_crash_are_picked_up_again(self):
        self.batch()
        item = self.add({"titles": ["A title that is long enough"]})
        self.store.conn.execute("UPDATE import_items SET state='resolving' WHERE id=?", (item["id"],))
        self.store.conn.commit()
        self.assertEqual(self.imp.resolve(self.batch_id), "review")
        self.assertEqual(self.state(item)["state"], "unmatched")

    def test_only_one_resolver_runs_at_a_time(self):
        self.batch()
        self.add({"titles": ["A title that is long enough"]})
        other = LibraryImport(self.data, Store(self.data / "paperdighelper.sqlite"), self.client)
        gate, release = threading.Event(), threading.Event()
        original = self.client.title_lookup

        def slow(title):
            gate.set()
            release.wait(5)
            return original(title)
        self.client.title_lookup = slow
        thread = threading.Thread(target=lambda: self.imp.resolve(self.batch_id))
        thread.start()
        self.assertTrue(gate.wait(5))
        try:
            with self.assertRaises(ValueError):
                other.resolve(self.batch_id)
        finally:
            release.set()
            thread.join(5)

    def test_a_second_batch_asked_to_match_while_another_runs_is_paused_with_a_reason(self):
        self.batch()
        self.add({"titles": ["A title that is long enough"]})
        mine = self.batch_id
        other_id = self.imp.create_batch(self.project, "folder", "r", {})["id"]
        data = pdf(900)
        self.imp.add_pdf(other_id, "r/z.pdf", io.BytesIO(data), len(data), 1, {"titles": ["Another title that is long"]})
        gate, release = threading.Event(), threading.Event()
        original = self.client.title_lookup

        def slow(title):
            gate.set()
            release.wait(5)
            return original(title)
        self.client.title_lookup = slow
        thread = threading.Thread(target=lambda: self.imp.resolve(mine))
        thread.start()
        self.assertTrue(gate.wait(5))
        try:
            with self.assertRaises(ValueError):
                LibraryImport(self.data, Store(self.data / "paperdighelper.sqlite"), self.client).resolve(other_id)
            self.assertEqual(self.imp.batch(other_id)["status"], "paused")
            self.assertEqual(self.imp.batch(other_id)["pause_reason"], "busy")
            self.assertEqual(self.imp.batch(mine)["status"], "resolving")   # the running batch is not touched
        finally:
            release.set()
            thread.join(5)
        self.assertEqual(self.imp.batch(mine)["status"], "review")

    def test_asking_the_same_running_batch_again_leaves_its_status_alone(self):
        self.batch()
        self.add({"titles": ["A title that is long enough"]})
        gate, release = threading.Event(), threading.Event()
        original = self.client.title_lookup

        def slow(title):
            gate.set()
            release.wait(5)
            return original(title)
        self.client.title_lookup = slow
        thread = threading.Thread(target=lambda: self.imp.resolve(self.batch_id))
        thread.start()
        self.assertTrue(gate.wait(5))
        try:
            with self.assertRaises(ValueError):
                LibraryImport(self.data, Store(self.data / "paperdighelper.sqlite"), self.client).resolve(self.batch_id)
            self.assertEqual(self.imp.batch(self.batch_id)["status"], "resolving")
        finally:
            release.set()
            thread.join(5)

    def test_a_batch_discarded_while_it_is_matched_stays_discarded(self):
        self.batch()
        self.add({"titles": ["A title that is long enough"]})
        gate, release = threading.Event(), threading.Event()
        original = self.client.title_lookup

        def slow(title):
            gate.set()
            release.wait(5)
            return original(title)
        self.client.title_lookup = slow
        thread = threading.Thread(target=lambda: self.imp.resolve(self.batch_id))
        thread.start()
        self.assertTrue(gate.wait(5))
        LibraryImport(self.data, Store(self.data / "paperdighelper.sqlite"), self.client).discard(self.batch_id)
        release.set()
        thread.join(5)
        self.assertEqual(self.imp.batch(self.batch_id)["status"], "discarded")
        self.assertFalse((self.data / "imports" / "batches" / self.batch_id).exists())

    def test_a_batch_cannot_be_resolved_after_it_is_closed(self):
        self.batch()
        self.imp.discard(self.batch_id)
        with self.assertRaises(ValueError):
            self.imp.resolve(self.batch_id)


class SettleTests(Base):
    """When OpenAlex's allowance is used up the person must not be stuck: the rest can be imported as it is."""

    def paused_batch(self):
        self.batch()
        self.add({"titles": ["First long enough title"]})
        self.add(None, name="scan.pdf")
        self.client.limit = {"remaining": 0, "observed_at": time.time(), "reset_seconds": 3600}
        self.assertEqual(self.imp.resolve(self.batch_id), "paused")

    def test_what_is_still_waiting_is_kept_as_plain_pdfs_and_the_batch_can_be_committed(self):
        self.paused_batch()
        with self.assertRaises(ValueError):
            self.imp.commit(self.batch_id)
        self.imp.settle_rest(self.batch_id)
        detail = self.imp.batch(self.batch_id)
        self.assertEqual((detail["status"], detail["counts"]), ("review", {"unmatched": 2}))
        self.assertEqual(self.client.calls, [])
        self.assertEqual(self.imp.commit(self.batch_id)["unresolved"], 2)

    def test_an_export_entry_still_waiting_keeps_the_exports_own_record(self):
        self.batch()
        self.imp.add_sidecar(self.batch_id, "x.bib", b"@article{a,\n title = {An entry from the export},\n doi = {10.1000/e1},\n}\n")
        self.imp.conn.execute("UPDATE import_batches SET options=? WHERE id=?", (json.dumps({"online": True, "include_fileless": True}), self.batch_id))
        self.imp.conn.commit()
        self.client.limit = {"remaining": 0, "observed_at": time.time(), "reset_seconds": 3600}
        self.assertEqual(self.imp.resolve(self.batch_id), "paused")
        self.imp.settle_rest(self.batch_id)
        item = self.imp.batch(self.batch_id)["items"][0]
        self.assertEqual((item["state"], item["match_source"], item["paper"]["title"]), ("matched", "sidecar", "An entry from the export"))

    def test_it_will_not_run_while_another_resolver_holds_openalex(self):
        self.paused_batch()
        gate, release = threading.Event(), threading.Event()
        other = LibraryImport(self.data, Store(self.data / "paperdighelper.sqlite"), self.client)
        with other._single_flight():
            with self.assertRaises(ValueError):
                self.imp.settle_rest(self.batch_id)
        self.assertEqual(self.imp.batch(self.batch_id)["counts"], {"pending": 2})

    def test_a_closed_batch_cannot_be_settled(self):
        self.paused_batch()
        self.imp.discard(self.batch_id)
        with self.assertRaises(ValueError):
            self.imp.settle_rest(self.batch_id)


if __name__ == "__main__":
    unittest.main()

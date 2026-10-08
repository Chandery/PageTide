import tempfile
import unittest
from pathlib import Path

from app.db import Store


class ReaderContextFixTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(Path(self.tmp.name) / 'library.sqlite')
        self.store.init()
        self.addCleanup(self.store.close)
        self.store.upsert_papers([{'key': 'a', 'title': 'A'}, {'key': 'b', 'title': 'B'}])

    def test_new_session_retains_audit_history_but_removes_it_from_next_prompt(self):
        from app import reader_context
        self.store.add_qa('a', 'user', 'old context')
        before = reader_context.session(self.store, 'a', None)
        self.assertEqual(len(reader_context.history(self.store, 'a', None, before)), 1)
        after = reader_context.new_session(self.store, 'a', None)
        self.assertNotEqual(before['id'], after['id'])
        self.assertEqual(reader_context.history(self.store, 'a', None, after), [])
        self.assertEqual(len(self.store.qa_history('a')), 1)
        self.store.add_qa('a', 'user', 'new context')
        self.assertEqual(reader_context.history(self.store, 'a', None, after)[0]['content'], 'new context')
        with self.assertRaisesRegex(ValueError, '会话'):
            reader_context.assert_session(self.store, 'a', None, before)

    def test_evidence_key_project_and_pdf_version_are_verified(self):
        from app import reader_context
        self.store.record_pdf('a', 'a.pdf', sha256='a' * 64)
        good = {'key': 'a', 'project_id': 'p', 'pdf_sha256': 'a' * 64}
        reader_context.validate_evidence(self.store, 'a', 'p', good)
        for field, value in [('key', 'b'), ('project_id', 'q'), ('pdf_sha256', 'b' * 64)]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                reader_context.validate_evidence(self.store, 'a', 'p', {**good, field: value})

    def test_pdf_replacement_starts_a_new_context_without_deleting_old_answers(self):
        from app import reader_context
        self.store.record_pdf('a', 'a.pdf', sha256='a' * 64)
        before = reader_context.session(self.store, 'a', None)
        self.store.add_qa('a', 'assistant', 'An answer about PDF version one')
        self.store.record_pdf('a', 'b.pdf', sha256='b' * 64)
        with self.assertRaisesRegex(ValueError, '会话'):
            reader_context.assert_session(self.store, 'a', None, before)
        after = reader_context.session(self.store, 'a', None)
        self.assertNotEqual(before['id'], after['id'])
        self.assertEqual(reader_context.history(self.store, 'a', None, after), [])
        self.assertEqual(self.store.qa_history('a')[0]['content'], 'An answer about PDF version one')

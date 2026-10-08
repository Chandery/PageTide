"""Audit regressions: identities, immutable archives, recovery and real timing gates."""
import hashlib
import io
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from app import creation, library_import, reference_files
from app.db import Store
from app.library_import import LibraryImport
from app.pdf_fetch import Fetcher, PdfFetchError
from app.project import ProjectManager
from tests.library_import_fixtures import FakeClient, work
from tests.pdf_fixture import minimal_pdf


class ImportAuditRepairs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data = Path(self.tmp.name)
        self.store = Store(self.data / 'db.sqlite')
        self.store.init()
        self.addCleanup(self.store.conn.close)
        self.project = ProjectManager(self.store).create_project('public import probe')
        self.client = FakeClient()
        self.imp = LibraryImport(self.data, self.store, self.client)

    def batch(self):
        return self.imp.create_batch(self.project, 'folder', 'r', {'online': False, 'include_fileless': True})['id']

    def add(self, batch, label='a', hints=None, path='r/paper.pdf'):
        data = minimal_pdf(label)
        return self.imp.add_pdf(batch, path, io.BytesIO(data), len(data), 7, hints)

    def other(self):
        store = Store(self.data / 'db.sqlite')
        self.addCleanup(store.conn.close)
        return LibraryImport(self.data, store, self.client)

    def test_i01_failed_writer_cannot_remove_a_successful_batch_archive(self):
        a, b = self.batch(), self.batch()
        self.add(a); self.add(b)
        self.imp.resolve(a); self.imp.resolve(b)
        copied, release, errors = threading.Event(), threading.Event(), []
        archive = library_import.archive_pdf

        def pause_archive(*args):
            path = archive(*args)
            if threading.current_thread().name == 'failing-a':
                copied.set()
                if not release.wait(5):
                    raise RuntimeError('test barrier timeout')
            return path

        def writer():
            s = Store(self.data / 'db.sqlite')
            try:
                imp = LibraryImport(self.data, s, self.client)
                with mock.patch.object(s, 'record_pdf', side_effect=RuntimeError('injected DB failure')):
                    imp.commit(a)
            except BaseException as exc:
                errors.append(exc)
            finally:
                s.conn.close()

        with mock.patch.object(library_import, 'archive_pdf', pause_archive):
            t = threading.Thread(target=writer, name='failing-a')
            t.start()
            try:
                self.assertTrue(copied.wait(5))
                self.imp.commit(b)
            finally:
                release.set(); t.join(5)
        self.assertFalse(t.is_alive())
        self.assertTrue(errors)
        path = Path(self.store.conn.execute('SELECT path FROM pdfs').fetchone()[0])
        self.assertTrue(path.is_file())
        self.assertEqual(path.read_bytes(), minimal_pdf('a'))
        self.assertEqual(self.imp.batch(b)['status'], 'committed')
        self.assertEqual(self.imp.batch(a)['status'], 'review')

    def test_i02_local_identifier_title_conflict_requires_choice(self):
        self.store.upsert_papers([{'key': 'https://doi.org/10.1000/med', 'doi': 'https://doi.org/10.1000/med',
                                  'title': 'Lung cancer resistance under immune checkpoint therapy'}], project_id=self.project)
        b = self.batch()
        i = self.add(b, hints={'doi': '10.1000/med', 'titles': ['Sulfide electrolyte cathode interface decomposition']})
        self.imp.resolve(b)
        got = self.imp.item(b, i['id'])
        self.assertEqual(got['state'], 'needs_choice')
        self.assertIsNone(got['paper_key'])
        self.assertIn('不一致', got['error'])

    def test_i03_and_i04_conflicting_and_corrected_sidecar_sources_are_visible(self):
        b = self.batch(); i = self.add(b)
        def bib(doi, title):
            return ('@article{x,title={' + title + '},doi={' + doi + '},file={paper.pdf}}').encode()
        self.imp.add_sidecar(b, 'old.bib', bib('10.1000/one', 'First reference title'))
        self.imp.resolve(b)
        self.imp.add_sidecar(b, 'corrected.bib', bib('10.1000/two', 'Corrected reference title'))
        self.imp.resolve(b)
        got = self.imp.item(b, i['id'])
        self.assertEqual(got['state'], 'needs_choice')
        self.assertEqual({c['paper']['key'] for c in got['candidates']},
                         {'https://doi.org/10.1000/one', 'https://doi.org/10.1000/two'})
        self.assertIn('冲突', got['error'])
        self.assertEqual(len(self.imp.batch(b)['items']), 2)

    def test_i05_archive_failure_retains_batch_and_reupload_recovers_all(self):
        b = self.batch(); self.add(b, 'good'); bad = self.add(b, 'bad', path='r/bad.pdf')
        self.imp.resolve(b)
        (self.imp._staging(b) / (bad['sha256'] + '.pdf')).unlink()
        with self.assertRaisesRegex(ValueError, '归档失败'):
            self.imp.commit(b)
        self.assertEqual(self.store.conn.execute('SELECT COUNT(*) FROM project_library').fetchone()[0], 0)
        self.assertEqual(self.imp.batch(b)['status'], 'review')
        self.assertTrue(self.imp._staging(b).exists())
        with self.assertRaisesRegex(ValueError, '失败项'):
            self.imp.commit(b)
        self.add(b, 'bad', path='r/bad.pdf')
        self.imp.resolve(b)
        self.assertEqual(self.imp.commit(b)['new_papers'], 2)

    def test_i06_late_upload_after_discard_never_registers_success(self):
        b = self.batch(); other = self.other(); stream = self.imp._stream
        def finish_then_discard(*args):
            result = stream(*args)
            other.discard(b)
            return result
        with mock.patch.object(self.imp, '_stream', finish_then_discard):
            with self.assertRaisesRegex(ValueError, '已关闭'):
                self.add(b)
        self.assertEqual(self.imp.batch(b)['items'], [])
        self.assertFalse(self.imp._staging(b).exists())

    def test_i07_pending_lookup_blocks_commit_and_cannot_write_after_commit(self):
        b = self.batch(); i = self.add(b); self.imp.resolve(b)
        started, release, errors = threading.Event(), threading.Event(), []
        def lookup(_):
            started.set(); release.wait(5)
            return work(99, 'Public lookup title')
        self.client.work = lookup
        def review():
            s = Store(self.data / 'db.sqlite')
            try:
                LibraryImport(self.data, s, self.client).act(b, i['id'], 'lookup', text='10.1000/99')
            except BaseException as exc:
                errors.append(exc)
            finally:
                s.conn.close()
        t = threading.Thread(target=review); t.start()
        try:
            self.assertTrue(started.wait(5))
            with self.assertRaises(ValueError):
                self.imp.commit(b)
        finally:
            release.set(); t.join(5)
        self.assertEqual(errors, [])
        self.imp.commit(b)
        before = self.imp.item(b, i['id'])
        self.imp._set(i['id'], 'matched', paper={'key': 'foreign', 'title': 'late'})
        self.assertEqual(self.imp.item(b, i['id']), before)
        self.assertEqual(len(self.imp.placements(b)), 1)

    def test_i08_status_counts_share_one_snapshot(self):
        b = self.batch(); i = self.add(b); other = self.other()
        self.imp._touch(b, status='resolving'); self.store.conn.commit()
        counts = self.imp.counts
        def finish_between_reads(batch):
            other._set(i['id'], 'unmatched', paper={'key': 'pdf:' + i['sha256'], 'title': 'a'})
            other._touch(b, status='review'); other.conn.commit()
            return counts(batch)
        with mock.patch.object(self.imp, 'counts', finish_between_reads):
            first = self.imp.batch(b)
        self.assertEqual((first['status'], first['counts']), ('resolving', {'pending': 1}))
        self.assertEqual(self.imp.batch(b)['status'], 'review')

    def test_i09_incomplete_ris_tail_is_reported(self):
        got = reference_files.parse_ris('TY  - JOUR\nTI  - Good\nER  -\nTY  - JOUR\nTI  - Missing end\n')
        self.assertEqual(len(got['entries']), 1)
        self.assertTrue(got['errors'])
        self.assertIn('ER', got['errors'][0])

    def test_i10_two_word_title_detects_identifier_metadata_pollution(self):
        b = self.imp.create_batch(self.project, 'files', '', {'online': True})['id']
        i = self.add(b, hints={'doi': '10.1000/wm', 'titles': ['World Models']})
        self.client.dois['https://doi.org/10.1000/wm'] = work(1, 'VOLE Field efficient semantic scene reconstruction', doi='https://doi.org/10.1000/wm')
        self.imp.resolve(b)
        self.assertEqual(self.imp.item(b, i['id'])['state'], 'needs_choice')

    def test_i11_same_metadata_resend_checks_actual_content(self):
        b = self.batch(); a = self.add(b, 'a'); changed = self.add(b, 'b')
        self.assertEqual(a['size'], changed['size'])
        self.assertNotEqual(a['sha256'], changed['sha256'])
        self.assertEqual(changed['sha256'], hashlib.sha256(minimal_pdf('b')).hexdigest())

    def test_b22_header_only_pdf_rejected_at_upload_and_download(self):
        raw = b'%PDF-1.4\n1 0 obj <<>> endobj\n'
        with self.assertRaises(ValueError):
            creation.import_pdf(self.data, raw)
        with self.assertRaises(ValueError):
            self.imp.add_pdf(self.batch(), 'broken.pdf', io.BytesIO(raw), len(raw))
        class Response(io.BytesIO):
            headers = {}
            def geturl(self): return 'https://example.org/a.pdf'
        with self.assertRaises(PdfFetchError):
            Fetcher(self.data / 'download')._save(Response(raw), 'https://example.org/a.pdf', 'test')
        self.assertEqual(list((self.data / 'download').glob('*')), [])

    def test_file_capacity_rechecked_after_streaming(self):
        b = self.batch()
        original = self.imp._stream
        def concurrent_upload(*args):
            result = original(*args)
            other = self.other()
            raw = minimal_pdf('other')
            other.add_pdf(b, 'other.pdf', io.BytesIO(raw), len(raw))
            return result
        with mock.patch.object(library_import, 'MAX_FILES', 1), mock.patch.object(self.imp, '_stream', side_effect=concurrent_upload):
            with self.assertRaisesRegex(ValueError, '最多导入 1'):
                self.add(b)
        self.assertEqual(len(self.imp.batch(b)['items']), 1)

    def test_valid_large_xref_and_incremental_trailer(self):
        from app.pdf_validation import validate_pdf
        raw = minimal_pdf('xref')
        start = raw.index(b'xref\n')
        prefix = raw[:start]
        rows = raw[start:raw.index(b'trailer\n')].replace(b'0 6\n', b'0 3506\n')
        rows += b'0000000000 00000 f \n' * 3500
        large = prefix + rows + b'trailer\n<< /Size 3506 /Root 1 0 R >>\nstartxref\n' + str(start).encode() + b'\n%%EOF\n'
        self.assertTrue(validate_pdf(large))
        previous = int(raw.rsplit(b'startxref\n', 1)[1].split()[0])
        incremental = raw + b'xref\n0 1\n0000000000 65535 f \ntrailer\n<< /Size 6 /Prev ' + str(previous).encode() + b' >>\nstartxref\n' + str(len(raw)).encode() + b'\n%%EOF\n'
        self.assertTrue(validate_pdf(incremental))

    def test_xref_stream_fields_after_long_index(self):
        from app.pdf_validation import validate_pdf
        raw = minimal_pdf('stream')
        offset = len(raw)
        # Envelope regression: a large legal dictionary order must be accepted.
        # Strict rendering of a complete stream counterpart is independently
        # checked with 3500 real annotations in review evidence.
        dictionary = b'6 0 obj\n<< /Index [' + b'0 1 ' * 10000 + b'] /Type /XRef /Root 1 0 R /Length 0 >>\nstream\n\nendstream\nendobj\n'
        stream = raw + dictionary + b'startxref\n' + str(offset).encode() + b'\n%%EOF\n'
        self.assertTrue(validate_pdf(stream))

    def test_i03_i04_manual_choice_and_exclusion_survive_more_resolution(self):
        b = self.batch(); i = self.add(b)
        def bib(doi,title): return ('@article{x,title={'+title+'},doi={'+doi+'},file={paper.pdf}}').encode()
        self.imp.add_sidecar(b,'first.bib',bib('10.1000/one','First title'))
        self.imp.resolve(b)
        self.imp.add_sidecar(b,'correct.bib',bib('10.1000/two','Corrected title'))
        self.imp.resolve(b)
        picked = self.imp.act(b,i['id'],'pick',index=1)
        self.add(b,'extra',path='r/extra.pdf'); self.imp.resolve(b)
        still = self.imp.item(b,i['id'])
        self.assertEqual(still['state'],'matched')
        self.assertEqual(still['paper']['key'],picked['paper']['key'])
        self.imp.act(b,i['id'],'exclude'); self.imp.resolve(b)
        self.assertEqual(self.imp.item(b,i['id'])['state'],'excluded')
        self.imp.add_sidecar(b,'third.bib',bib('10.1000/three','Third new identity'))
        self.imp.resolve(b)
        self.assertEqual(self.imp.item(b,i['id'])['state'],'excluded')
        self.assertEqual(len(self.imp.item(b,i['id'])['candidates']),3)
        self.imp.act(b,i['id'],'include')
        self.assertEqual(self.imp.item(b,i['id'])['state'],'needs_choice')

    def test_join_phase_claim_blocks_commit_until_metadata_is_settled(self):
        b=self.imp.create_batch(self.project,'folder','r',{'online':False,'include_fileless':False})['id']
        self.imp.add_sidecar(b,'refs.bib',b'@article{x,title={Public reference},doi={10.1000/one},file={late.pdf}}')
        self.imp.resolve(b)  # automatically excluded fileless source, still recoverable
        i=self.add(b,path='r/late.pdf'); self.imp.act(b,i['id'],'unresolved')
        entered,release,errors=threading.Event(),threading.Event(),[]
        def worker():
            other=self.other(); original=other._match_file
            def pause(*args):entered.set(); release.wait(3); return original(*args)
            try:
                with mock.patch.object(other,'_match_file',side_effect=pause):
                    other._join_sidecar(b,{'include_fileless':False},'r')
            except Exception as e:errors.append(e)
        t=threading.Thread(target=worker);t.start();self.assertTrue(entered.wait(2))
        try:
            with self.assertRaisesRegex(ValueError,'正在处理'):self.imp.commit(b)
        finally:release.set();t.join(4)
        self.assertFalse(errors);self.assertFalse(t.is_alive())
        self.imp.commit(b)
        self.assertEqual(self.imp.batch(b)['status'],'committed')
        self.assertIsNotNone(self.imp.item(b,i['id'])['entry'])

    def test_explicitly_excluded_reference_is_not_rebound_to_pdf(self):
        b=self.batch();i=self.add(b)
        self.imp.act(b,i['id'],'unresolved')
        self.imp.add_sidecar(b,'refs.bib',b'@article{x,title={Excluded reference},doi={10.1000/one},file={paper.pdf}}')
        entry=next(x for x in self.imp.batch(b)['items'] if x['kind']=='entry')
        self.imp.act(b,entry['id'],'exclude');self.imp.resolve(b)
        self.assertIsNone(self.imp.item(b,i['id'])['entry'])
        self.assertEqual(self.imp.item(b,entry['id'])['state'],'excluded')

    def test_old_network_metadata_cannot_bind_reuploaded_pdf(self):
        b=self.imp.create_batch(self.project,'folder','r',{'online':True})['id']
        old=self.add(b,'old',hints={'doi':'10.1000/old','titles':['Visual planning world models']})
        self.client.dois['https://doi.org/10.1000/old']=work(1,'Visual planning world models',doi='https://doi.org/10.1000/old')
        self.client.dois['https://doi.org/10.1000/new']=work(2,'Sulfide lithium interface stability',doi='https://doi.org/10.1000/new')
        entered,release,errors=threading.Event(),threading.Event(),[]
        original=self.client.works_by_dois
        def pause(dois):entered.set(); release.wait(3);return original(dois)
        def worker():
            other=self.other()
            try:
                with mock.patch.object(self.client,'works_by_dois',side_effect=pause):other.resolve(b)
            except Exception as e:errors.append(e)
        t=threading.Thread(target=worker);t.start();self.assertTrue(entered.wait(2))
        try:
            new=self.add(b,'new',hints={'doi':'10.1000/new','titles':['Sulfide lithium interface stability']})
        finally:release.set();t.join(4)
        self.assertFalse(errors);self.assertFalse(t.is_alive())
        current=self.imp.item(b,old['id']);self.assertEqual(current['state'],'pending')
        self.assertEqual(current['sha256'],new['sha256']);self.assertIsNone(current['paper'])
        self.assertEqual(self.imp.batch(b)['pause_reason'],'content_changed')
        self.imp.resolve(b);self.imp.commit(b)
        key=self.imp.item(b,old['id'])['paper_key']
        self.assertEqual(key,'https://doi.org/10.1000/new')
        path=self.store.conn.execute('SELECT path FROM pdfs WHERE paper_key=?',(key,)).fetchone()[0]
        self.assertEqual(hashlib.sha256(Path(path).read_bytes()).hexdigest(),new['sha256'])

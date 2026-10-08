import json
import sqlite3
import unittest
from unittest import mock

import test_app_server as smoke
from app import server


class ReaderHTTPFixTests(unittest.TestCase):
    setUp = smoke.ServerSmokeTests.setUp
    _get = smoke.ServerSmokeTests._get
    _post = smoke.ServerSmokeTests._post

    def test_full_export_contains_both_projects_and_every_database_table(self):
        first = self._post('/api/projects', {'name': 'CS', 'keywords': []})[1]['project_id']
        second = self._post('/api/projects', {'name': 'Medicine', 'keywords': []})[1]['project_id']
        app = server.make_app(str(self.root))
        app.store.upsert_papers([{'key': 'a', 'title': 'A'}])
        app.store.add_qa('a', 'user', 'Export this question', project_id=first)
        app.store.set_setting('route_' + second, {'revision': 3, 'graph': {'nodes': []}})
        tables = {row[0] for row in app.store.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        app.store.close()
        status, raw = self._get('/api/export?project_id=' + first)
        data = json.loads(raw)
        self.assertEqual(status, 200); self.assertEqual(data['scope'], 'all-projects')
        self.assertEqual(set(data['database']['tables']), tables)
        from app.local_snapshot import restore_database
        restored = restore_database(data, self.root / 'verification-only')
        with sqlite3.connect(restored) as copy:
            ids = {row[0] for row in copy.execute('SELECT id FROM projects')}
            self.assertTrue({first, second}.issubset(ids))
            self.assertEqual(copy.execute('SELECT COUNT(*) FROM qa_history').fetchone()[0], 1)
            self.assertEqual(copy.execute('SELECT value FROM settings WHERE key=?', ('route_' + second,)).fetchone()[0], '{"revision": 3, "graph": {"nodes": []}}')

    def test_reset_has_a_durable_receipt_and_keeps_history_out_of_next_request(self):
        app = server.make_app(str(self.root)); app.store.upsert_papers([{'key': 'a', 'title': 'A'}])
        app.store.add_qa('a', 'user', 'old marker'); app.store.close()
        old = json.loads(self._get('/api/qa/session?key=a')[1])['session']['id']
        status, reset = self._post('/api/qa/session', {'key': 'a'})
        self.assertEqual(status, 200); self.assertNotEqual(reset['session']['id'], old)
        current = json.loads(self._get('/api/qa/session?key=a')[1])['session']['id']
        self.assertEqual(current, reset['session']['id'])
        result = {'ok': True, 'content': '{"answer":"Supported answer","followups":[]}',
                  'usage': {'total_tokens': 1}, 'usd': 0, 'model': 'test'}
        with mock.patch('app.gateway.Gateway.call', return_value=result) as gateway:
            status, answer = self._post('/api/qa', {'key': 'a', 'question': 'new marker', 'session_id': current})
            self.assertEqual(status, 200); self.assertTrue(answer['ok'])
            self.assertNotIn('old marker', str(gateway.call_args))
            status, _ = self._post('/api/qa', {'key': 'a', 'question': 'stale request', 'session_id': old})
            self.assertEqual(status, 400); self.assertEqual(gateway.call_count, 1)

    def test_wrong_paper_or_pdf_evidence_never_calls_gateway(self):
        app = server.make_app(str(self.root)); app.store.upsert_papers([{'key': 'a', 'title': 'A'}])
        app.store.record_pdf('a', 'a.pdf', sha256='a' * 64); app.store.close()
        with mock.patch('app.gateway.Gateway.call') as gateway:
            for evidence in (['wrong type'], {'key':'b','project_id':None,'pdf_sha256':'a'*64},
                             {'key':'a','project_id':None,'pdf_sha256':'b'*64}):
                status, _ = self._post('/api/qa', {'key':'a','question':'Q','selection':'quote','reader_context':evidence})
                self.assertEqual(status,400)
            gateway.assert_not_called()
        status, _ = self._get('/api/pdf/view?key=a&sha256=' + 'b' * 64)
        self.assertEqual(status, 409)

    def test_new_session_during_model_result_rejects_late_history_write(self):
        app = server.make_app(str(self.root)); app.store.upsert_papers([{'key':'a','title':'A'}]); app.store.close()
        def delayed_result(*args, **kwargs):
            reset = server.make_app(str(self.root))
            from app.reader_context import new_session
            new_session(reset.store, 'a', None); reset.store.close()
            return {'ok':True,'content':'{"answer":"late answer","followups":[]}',
                    'usage':{'total_tokens':1},'usd':0,'model':'test'}
        with mock.patch('app.gateway.Gateway.call', side_effect=delayed_result):
            status, body = self._post('/api/qa', {'key':'a','question':'Q'})
        self.assertEqual(status,400); self.assertIn('会话',body['error'])
        app = server.make_app(str(self.root))
        self.assertEqual(app.store.qa_history('a'), []); app.store.close()

    def test_cache_failure_reports_failure_and_location_is_actual(self):
        cache = self.root / '.local/app/cache'; cache.mkdir(parents=True, exist_ok=True)
        (cache / 'source.json').write_text('{}')
        status, raw = self._get('/api/data-location')
        self.assertEqual(status, 200); self.assertEqual(json.loads(raw)['cache_dir'], str(cache.resolve()))
        with mock.patch('shutil.rmtree', side_effect=PermissionError('test refusal')):
            status, data = self._post('/api/cache', {'_method':'DELETE'})
        self.assertEqual(status,500); self.assertIn('error',data)
        status, data = self._post('/api/cache', {'_method':'DELETE'})
        self.assertEqual(status,200); self.assertIn('pdf-archives',data['preserved'])

    def test_theme_merge_preserves_other_settings_and_rejects_invalid_values(self):
        self._post('/api/user_settings', {'settings': {'recommendCount': 1, 'theme': 'dark'}})
        status, _ = self._post('/api/user_settings', {'settings': {'theme':'light'}, 'merge':True})
        self.assertEqual(status,200)
        settings = json.loads(self._get('/api/user_settings')[1])['settings']
        self.assertEqual(settings, {'recommendCount':1,'theme':'light'})
        status, _ = self._post('/api/user_settings', {'settings': {'theme':'INVALID'}})
        self.assertEqual(status,400)
        self.assertEqual(json.loads(self._get('/api/user_settings')[1])['settings'], settings)

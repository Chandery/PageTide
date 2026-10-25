"""Reader annotations: highlights with a note, kept per PDF file version, editable and deletable."""
import json
import unittest

import test_app_server as smoke
from app import annotations, server

SHA = 'a' * 64
BOX = [{'p': 2, 'x0': 0.1, 'y0': 0.2, 'x1': 0.6, 'y1': 0.23}, {'p': 2, 'x0': 0.1, 'y0': 0.24, 'x1': 0.4, 'y1': 0.27}]


class AnnotationHTTPTests(unittest.TestCase):
    setUp = smoke.ServerSmokeTests.setUp
    _get = smoke.ServerSmokeTests._get
    _post = smoke.ServerSmokeTests._post

    def seed(self, sha=SHA):
        app = server.make_app(str(self.root))
        app.store.upsert_papers([{'key': 'a', 'title': 'A'}])
        app.store.record_pdf('a', 'a.pdf', sha256=sha)
        app.store.close()

    def listed(self, sha=SHA):
        status, raw = self._get(f'/api/annotations?key=a&sha256={sha}')
        self.assertEqual(status, 200)
        return json.loads(raw)['items']

    def test_highlight_with_note_survives_reopen_then_edits_and_deletes(self):
        self.seed()
        status, made = self._post('/api/annotations', {'op': 'create', 'key': 'a', 'sha256': SHA, 'rects': BOX,
                                                       'quote': 'attention is all', 'comment': '核心假设', 'color': 'green'})
        self.assertEqual(status, 200)
        self.assertEqual((made['page'], made['color'], made['comment']), (2, 'green', '核心假设'))
        self.assertEqual(self.listed(), [made])                         # a new request (a reopened reader) sees it
        status, edited = self._post('/api/annotations', {'op': 'update', 'id': made['id'], 'comment': '改过', 'color': 'blue'})
        self.assertEqual(status, 200)
        self.assertEqual((edited['comment'], edited['color'], edited['quote']), ('改过', 'blue', 'attention is all'))
        status, _ = self._post('/api/annotations', {'op': 'delete', 'id': made['id']})
        self.assertEqual(status, 200)
        self.assertEqual(self.listed(), [])
        status, _ = self._post('/api/annotations', {'op': 'delete', 'id': made['id']})
        self.assertEqual(status, 400)

    def test_another_file_version_neither_shows_nor_accepts_them(self):
        self.seed()
        self._post('/api/annotations', {'op': 'create', 'key': 'a', 'sha256': SHA, 'rects': BOX})
        self.assertEqual(self.listed('b' * 64), [])
        status, body = self._post('/api/annotations', {'op': 'create', 'key': 'a', 'sha256': 'b' * 64, 'rects': BOX})
        self.assertEqual(status, 400)
        self.assertIn('版本', body['error'])
        self.assertEqual(len(self.listed()), 1)                         # the old version's annotation is kept

    def test_bad_input_is_refused(self):
        self.seed()
        bad = [{'op': 'create', 'key': 'missing', 'sha256': SHA, 'rects': BOX},
               {'op': 'create', 'key': 'a', 'sha256': SHA, 'rects': []},
               {'op': 'create', 'key': 'a', 'sha256': SHA, 'rects': [{'p': 1, 'x0': 0.5, 'y0': 0.1, 'x1': 0.4, 'y1': 0.2}]},
               {'op': 'create', 'key': 'a', 'sha256': SHA, 'rects': [{'p': 1, 'x0': 0, 'y0': 0, 'x1': 2, 'y1': 0.2}]},
               {'op': 'create', 'key': 'a', 'sha256': SHA, 'rects': [{'p': True, 'x0': 0, 'y0': 0, 'x1': .2, 'y1': .2}]},
               {'op': 'create', 'key': 'a', 'sha256': SHA, 'rects': BOX, 'color': 'black'},
               {'op': 'create', 'key': 'a', 'sha256': SHA, 'rects': BOX, 'comment': 'x' * (annotations.MAX_COMMENT + 1)},
               {'op': 'update', 'id': '../etc', 'comment': 'x'},
               {'op': 'rename'}]
        for body in bad:
            status, _ = self._post('/api/annotations', body)
            self.assertEqual(status, 400, body)
        self.assertEqual(self.listed(), [])
        status, _ = self._get('/api/annotations?key=a&sha256=nothex')
        self.assertEqual(status, 400)


if __name__ == '__main__':
    unittest.main()

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


class MentionTests(unittest.TestCase):
    """A note @s other notes inside its own text, written @[id] (the reader shows @3); the list is derived from the text."""
    setUp = smoke.ServerSmokeTests.setUp
    _get = smoke.ServerSmokeTests._get
    _post = smoke.ServerSmokeTests._post
    seed = AnnotationHTTPTests.seed
    listed = AnnotationHTTPTests.listed

    def make(self, comment='', key='a', sha=SHA):
        status, made = self._post('/api/annotations', {'op': 'create', 'key': key, 'sha256': sha, 'rects': BOX, 'comment': comment})
        self.assertEqual(status, 200)
        return made

    def write(self, note, comment):
        status, out = self._post('/api/annotations', {'op': 'update', 'id': note['id'], 'comment': comment})
        self.assertEqual(status, 200)
        return out

    def by_id(self):
        return {n['id']: n for n in self.listed()}

    def test_the_list_is_the_notes_written_into_the_text_in_order_once_each(self):
        self.seed()
        a, b, c = self.make('甲'), self.make('乙'), self.make('丙')
        self.assertEqual(a['mentions'], [])
        text = f"这一句回答了@[{c['id']}] 的问题，用了@[{b['id']}] 的观点，再看@[{c['id']}]"
        edited = self.write(a, text)
        self.assertEqual((edited['mentions'], edited['comment']), ([c['id'], b['id']], text))
        self.assertEqual(self.by_id()[a['id']]['mentions'], [c['id'], b['id']])          # a reopened reader sees it
        self.assertEqual(self._post('/api/annotations', {'op': 'update', 'id': a['id'], 'color': 'blue'})[1]['mentions'],
                         [c['id'], b['id']])                                              # a colour change leaves the @s alone
        self.assertEqual(self.write(a, '不再引用')['mentions'], [])                       # taking the @ out of the text takes the arrow away

    def test_only_other_notes_of_this_file_version_count(self):
        self.seed()
        a, b = self.make(), self.make()
        app = server.make_app(str(self.root))
        app.store.upsert_papers([{'key': 'z', 'title': 'Z'}])
        app.store.record_pdf('z', 'z.pdf', sha256='c' * 64)
        app.store.close()
        other = self.make(key='z', sha='c' * 64)
        junk = f"@[{a['id']}] @[{other['id']}] @[{'0' * 32}] @[nothex] @3 @[{b['id']}]"
        out = self.write(a, junk)
        self.assertEqual(out['mentions'], [b['id']])                                      # itself, another paper, unknown ids: no arrow
        self.assertEqual(out['comment'], junk)                                            # the text is kept as written

    def test_deleting_a_note_turns_the_references_to_it_into_a_marker(self):
        self.seed()
        a, b, c = self.make(), self.make(), self.make()
        self.write(a, f"见@[{b['id']}] 和@[{c['id']}]")
        self.write(c, f"同@[{b['id']}]")
        status, _ = self._post('/api/annotations', {'op': 'delete', 'id': b['id']})
        self.assertEqual(status, 200)
        notes = self.by_id()
        self.assertEqual((notes[a['id']]['comment'], notes[a['id']]['mentions']), (f"见{annotations.GONE} 和@[{c['id']}]", [c['id']]))
        self.assertEqual((notes[c['id']]['comment'], notes[c['id']]['mentions']), (f"同{annotations.GONE}", []))

    def test_an_older_table_without_the_column_gets_it_and_keeps_its_rows(self):
        self.seed()
        app = server.make_app(str(self.root))
        try:
            app.store.conn.executescript("DROP TABLE IF EXISTS annotations; CREATE TABLE annotations (id TEXT PRIMARY KEY, paper_key TEXT NOT NULL,"
                                         " pdf_sha256 TEXT NOT NULL, page INTEGER NOT NULL, rects TEXT NOT NULL, quote TEXT NOT NULL DEFAULT '',"
                                         " comment TEXT NOT NULL DEFAULT '', color TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);"
                                         " INSERT INTO annotations VALUES ('" + 'a' * 32 + "','a','" + SHA + "',1,'[]','q','old','yellow','t','t');")
            app.store.conn.commit()
        finally:
            app.store.close()
        self.assertEqual([(n['comment'], n['mentions']) for n in self.listed()], [('old', [])])

if __name__ == '__main__':
    unittest.main()

"""Local reading identity and durable conversation boundaries. No model calls."""
import hashlib
import json
import uuid


def _key(paper_key, project_id):
    identity = json.dumps([paper_key, project_id], ensure_ascii=False).encode()
    return 'qa_session_' + hashlib.sha256(identity).hexdigest()


def session(store, paper_key, project_id):
    # The legacy conversation is session zero until explicitly started anew.
    current = store.get_setting(_key(paper_key, project_id), {'id': 'legacy', 'cursor': 0, 'pdf_sha256': None})
    if current.get('pdf_sha256') != _pdf_version(store, paper_key):
        return new_session(store, paper_key, project_id)
    return current


def _pdf_version(store, paper_key):
    row = store.conn.execute('SELECT sha256 FROM pdfs WHERE paper_key=?', (paper_key,)).fetchone()
    return row['sha256'] if row else None


def new_session(store, paper_key, project_id):
    with store.conn:
        cursor = store.conn.execute('SELECT COALESCE(MAX(id),0) FROM qa_history').fetchone()[0]
        current = {'id': uuid.uuid4().hex, 'cursor': cursor, 'pdf_sha256': _pdf_version(store, paper_key)}
        store.conn.execute('INSERT INTO settings(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                           (_key(paper_key, project_id), json.dumps(current)))
    return current


def assert_session(store, paper_key, project_id, expected):
    current = store.get_setting(_key(paper_key, project_id), {'id': 'legacy', 'cursor': 0, 'pdf_sha256': None})
    if current != expected or _pdf_version(store, paper_key) != expected.get('pdf_sha256'):
        raise ValueError('阅读会话已变化，请在新会话中重新提问')


def history(store, paper_key, project_id, current, limit=None):
    """The current reading session's turns, oldest first; the whole session unless a limit is given."""
    rows = store.conn.execute('''SELECT role, content, created_at FROM qa_history
        WHERE paper_key IS ? AND project_id IS ? AND id>? ORDER BY id DESC LIMIT ?''',
        (paper_key, project_id, current['cursor'], -1 if limit is None else limit)).fetchall()
    return [dict(row) for row in reversed(rows)]


def validate_evidence(store, paper_key, project_id, evidence):
    if not isinstance(evidence, dict) or evidence.get('key') != paper_key or evidence.get('project_id') != project_id:
        raise ValueError('引用或页面与当前论文、项目不一致，请重新打开论文')
    if evidence.get('kind') == 'metadata':
        return
    digest = evidence.get('pdf_sha256')
    row = store.conn.execute('SELECT sha256 FROM pdfs WHERE paper_key=?', (paper_key,)).fetchone()
    if not isinstance(digest, str) or len(digest) != 64 or not row or row['sha256'] != digest:
        raise ValueError('PDF 版本已变化，请重新打开论文并选择引用或页面')

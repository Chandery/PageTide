"""Versioned, consistent local-state export; PDF archive bytes are a separate backup."""
import base64
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def create_snapshot(store, data_dir):
    root = Path(data_dir)
    if store.conn.in_transaction:
        raise ValueError('请先完成当前数据库操作，再导出一致性快照')
    with tempfile.TemporaryDirectory(prefix='pdh-export-') as directory:
        path = Path(directory) / 'snapshot.sqlite'
        with sqlite3.connect(path) as copy:
            store.conn.backup(copy)
            copy.execute('PRAGMA journal_mode=DELETE')
            names = [row[0] for row in copy.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
            counts = {name: copy.execute('SELECT COUNT(*) FROM "' + name.replace('"', '""') + '"').fetchone()[0] for name in names}
            integrity = copy.execute('PRAGMA integrity_check').fetchone()[0]
        copy.close()
        if integrity != 'ok':
            raise ValueError('数据库一致性检查失败，未导出')
        raw = path.read_bytes()
    files = {}
    for name in ('settings.json', 'usage.jsonl', 'usage-dev.jsonl', 'AI_DISABLED'):
        path = root / name
        if not path.is_file():
            continue
        if name == 'settings.json':
            settings = json.loads(path.read_text(encoding='utf-8'))
            files[name] = {key: value for key, value in settings.items() if key not in
                           {'apiKey', 'api_key', 'openalex_key', 'dailyLimit', 'aiRerank'}}
        else:
            files[name] = path.read_text(encoding='utf-8')
    return {'format': 'pagetide.local-snapshot', 'version': 1,
            'exported_at': datetime.now(timezone.utc).isoformat(), 'scope': 'all-projects',
            'includes': ['all-database-tables', 'projects', 'learning-maps', 'feedback-and-profile-versions',
                         'notes-and-history-and-drafts', 'qa-history-and-sessions', 'categories-and-undo',
                         'pdf-version-metadata', 'import-batch-state', 'settings-and-usage'],
            'excludes': ['provider-credentials', 'pdf-and-import-staging-file-bytes', 'source-cache'],
            'archive_note': 'PDF 与导入暂存原文件不在结构化快照中；完整迁移还需复制本机数据目录的 pdfs、seed-pdfs、imports 等文件目录。',
            'database': {'encoding': 'sqlite-base64', 'sha256': hashlib.sha256(raw).hexdigest(),
                         'tables': counts, 'bytes': len(raw), 'content': base64.b64encode(raw).decode('ascii')},
            'local_files': files}


def restore_database(snapshot, empty_directory):
    """Restore for verification/inspection only into a new directory, never over a library.

    The exported database retains PDF path metadata. Copy/remap archive files before
    using a restored library; this function never follows those paths or changes originals.
    """
    if snapshot.get('format') != 'pagetide.local-snapshot' or snapshot.get('version') != 1:
        raise ValueError('不支持的快照版本')
    target = Path(empty_directory)
    if target.exists():
        raise ValueError('恢复目录必须不存在，不能覆盖已有资料')
    database = snapshot['database']
    raw = base64.b64decode(database['content'], validate=True)
    if hashlib.sha256(raw).hexdigest() != database['sha256'] or len(raw) != database['bytes']:
        raise ValueError('快照校验失败')
    # Verify outside the requested directory; failed validation leaves no partial restoration.
    with tempfile.TemporaryDirectory(prefix='pdh-restore-check-') as temporary:
        path = Path(temporary) / 'snapshot.sqlite'; path.write_bytes(raw)
        with sqlite3.connect(f'file:{path}?mode=ro', uri=True) as copy:
            if copy.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('快照数据库损坏')
            for name, count in database['tables'].items():
                actual = copy.execute('SELECT COUNT(*) FROM "' + name.replace('"', '""') + '"').fetchone()[0]
                if actual != count:
                    raise ValueError('快照表记录数不一致')
        copy.close()
    # Validate before creating anything. Own only this newly created directory;
    # a pre-existing destination is never cleaned or overwritten.
    target.mkdir(parents=True, mode=0o700)
    restored = target / 'pagetide.sqlite'
    temporary = target / '.restore-partial.sqlite'
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'wb') as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, restored)
    except BaseException:
        shutil.rmtree(target)
        raise
    return restored

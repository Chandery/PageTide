"""Database migrations for multi-project support.

Each migration is a function that takes a connection and applies schema changes.
Migrations are tracked in a new `schema_version` table.
"""
import json
import sqlite3
import sys


def _log(message):
    """Progress goes to stderr: stdout carries JSON for the desktop worker."""
    print(message, file=sys.stderr, flush=True)


def now():
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def get_schema_version(conn):
    """Get current schema version, or 0 if not tracked yet."""
    try:
        row = conn.execute("SELECT MAX(version) AS version FROM schema_version").fetchone()
        return int(row[0]) if row and row[0] is not None else 0
    except sqlite3.OperationalError:
        # schema_version table doesn't exist yet
        return 0


def set_schema_version(conn, version):
    """Record that a migration has been applied."""
    conn.execute("INSERT INTO schema_version (version, applied_at) VALUES (?,?)", (version, now()))


_LEGACY_TABLES = ("papers", "feedback", "batches", "profile_versions", "library", "qa_history")


def _has_legacy_rows(conn):
    """True when any pre-project table already holds data (an upgrade, not a fresh install)."""
    for table in _LEGACY_TABLES:
        try:
            if conn.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone():
                return True
        except sqlite3.OperationalError:
            continue
    return False


def migrate_001_multi_project(conn):
    """Add multi-project support: projects table, project_id foreign keys, snapshots and reports."""

    # Create schema_version table if it doesn't exist
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER NOT NULL,
            applied_at TEXT NOT NULL
        )
    """)

    # Create projects table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            creation_mode TEXT CHECK(creation_mode IN ('quick', 'manual', 'ai_guided')),
            creation_timestamp TEXT NOT NULL,
            keywords TEXT,
            decay_window_days INTEGER DEFAULT 30,
            guidance_transcript TEXT,
            recommended_learning_path TEXT
        )
    """)

    # Pre-multi-project data needs a project to belong to; a fresh database has none and gets no project.
    default_project_id = "default_project"
    if _has_legacy_rows(conn):
        conn.execute("""
            INSERT OR IGNORE INTO projects (id, name, creation_mode, creation_timestamp, keywords)
            VALUES (?, ?, ?, ?, ?)
        """, (default_project_id, "默认项目", "manual", now(), json.dumps([])))

    # Add project_id to papers table
    try:
        conn.execute("ALTER TABLE papers ADD COLUMN project_id TEXT REFERENCES projects(id)")
    except sqlite3.OperationalError:
        pass  # Column already exists

    # Set all existing papers to default project
    conn.execute(f"UPDATE papers SET project_id = ? WHERE project_id IS NULL", (default_project_id,))

    # Add project_id to feedback table
    try:
        conn.execute("ALTER TABLE feedback ADD COLUMN project_id TEXT REFERENCES projects(id)")
    except sqlite3.OperationalError:
        pass  # Column already exists

    # Set all existing feedback to default project
    conn.execute(f"UPDATE feedback SET project_id = ? WHERE project_id IS NULL", (default_project_id,))

    # Add project_id to batches table
    try:
        conn.execute("ALTER TABLE batches ADD COLUMN project_id TEXT REFERENCES projects(id)")
    except sqlite3.OperationalError:
        pass  # Column already exists

    # Set all existing batches to default project
    conn.execute(f"UPDATE batches SET project_id = ? WHERE project_id IS NULL", (default_project_id,))

    # Create profile_snapshots table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS profile_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL REFERENCES projects(id),
            snapshot_timestamp TEXT NOT NULL,
            top_keywords TEXT NOT NULL,
            interest_distribution TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_project ON profile_snapshots(project_id)")

    # Create weekly_reports table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS weekly_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL REFERENCES projects(id),
            week_start TEXT NOT NULL,
            week_end TEXT NOT NULL,
            stats TEXT NOT NULL,
            keyword_changes TEXT,
            ai_analysis TEXT,
            generated_timestamp TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_reports_project ON weekly_reports(project_id)")

    # Migrate existing profile_versions to default project snapshots
    # Extract keywords from the most recent profile versions
    rows = conn.execute("SELECT id, created_at, data FROM profile_versions ORDER BY id").fetchall()
    for row in rows:
        try:
            profile_data = json.loads(row[2])
            keywords = profile_data.get("keywords", [])
            if keywords:
                top_keywords = {kw: 1.0 for kw in keywords[:20]}  # Take top 20 keywords
                conn.execute("""
                    INSERT INTO profile_snapshots (project_id, snapshot_timestamp, top_keywords, interest_distribution)
                    VALUES (?, ?, ?, ?)
                """, (default_project_id, row[1], json.dumps(top_keywords), json.dumps({})))
        except (json.JSONDecodeError, KeyError):
            pass  # Skip malformed profile data

    set_schema_version(conn, 1)


def migrate_002_shared_papers(conn):
    """Allow one canonical paper to belong to multiple project contexts."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS project_papers (
            project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            paper_key TEXT NOT NULL REFERENCES papers(key) ON DELETE CASCADE,
            relation_kind TEXT NOT NULL DEFAULT 'discovered',
            added_at TEXT NOT NULL,
            source_project_id TEXT REFERENCES projects(id),
            PRIMARY KEY (project_id, paper_key)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_project_papers_paper ON project_papers(paper_key)")
    conn.execute("""
        INSERT OR IGNORE INTO project_papers(project_id, paper_key, relation_kind, added_at)
        SELECT project_id, key,
               CASE WHEN group_name='seed' THEN 'seed' ELSE 'discovered' END,
               created_at
        FROM papers WHERE project_id IS NOT NULL
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS project_library (
            project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            paper_key TEXT NOT NULL REFERENCES papers(key) ON DELETE CASCADE,
            saved_at TEXT NOT NULL,
            note TEXT,
            PRIMARY KEY (project_id, paper_key)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_project_library_paper ON project_library(paper_key)")
    conn.execute("""
        INSERT OR IGNORE INTO project_library(project_id, paper_key, saved_at, note)
        SELECT p.project_id, l.paper_key, l.saved_at, l.note
        FROM library l JOIN papers p ON p.key=l.paper_key
        WHERE p.project_id IS NOT NULL
    """)
    set_schema_version(conn, 2)


def migrate_003_project_guidance(conn):
    """Persist resumable, pre-creation project guidance drafts."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS project_guidance_sessions (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('draft','confirmed','cancelled','failed')),
            transcript TEXT NOT NULL,
            draft TEXT NOT NULL,
            turn_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_guidance_status ON project_guidance_sessions(status, updated_at)")
    set_schema_version(conn, 3)


def migrate_004_project_scoped_qa(conn):
    """Keep personal paper Q&A history inside the project that created it."""
    try:
        conn.execute("ALTER TABLE qa_history ADD COLUMN project_id TEXT REFERENCES projects(id)")
    except sqlite3.OperationalError:
        pass
    conn.execute("UPDATE qa_history SET project_id='default_project' WHERE project_id IS NULL")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_qa_project_paper ON qa_history(project_id, paper_key, id)")
    set_schema_version(conn, 4)


def migrate_006_pdf_acquisition(conn):
    """Keep OpenAlex open-access facts per paper and provenance per archived PDF."""
    for table, column, kind in (("papers", "oa_json", "TEXT"), ("pdfs", "sha256", "TEXT"),
                                ("pdfs", "bytes", "INTEGER"), ("pdfs", "source_kind", "TEXT"),
                                ("pdfs", "license", "TEXT")):
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {kind}")
        except sqlite3.OperationalError as exc:
            if "duplicate column" not in str(exc).lower():
                raise  # a locked or read-only database must not be recorded as migrated
    set_schema_version(conn, 6)


def migrate_007_pdf_versions(conn):
    """Append-only history of archived PDFs, so replacing a paper's PDF never loses where the old one came from."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pdf_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paper_key TEXT NOT NULL, path TEXT NOT NULL, source_url TEXT, sha256 TEXT, bytes INTEGER,
            source_kind TEXT, license TEXT, fetched_at TEXT NOT NULL
        )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_pdf_versions_paper ON pdf_versions(paper_key, id)")
    conn.execute("""
        INSERT INTO pdf_versions (paper_key, path, source_url, sha256, bytes, source_kind, license, fetched_at)
        SELECT paper_key, path, source_url, sha256, bytes, source_kind, license, fetched_at FROM pdfs
        WHERE NOT EXISTS (SELECT 1 FROM pdf_versions v WHERE v.paper_key = pdfs.paper_key AND v.path = pdfs.path)""")
    set_schema_version(conn, 7)


def migrate_008_exposure_route(conn):
    """Remember, for each paper a batch showed, which concept of the learning map it was shown for (id, name and layer at that
    time, because ids are reused when a map is replaced) and why (route / remedial / explore)."""
    for column, kind in (("route_node", "TEXT"), ("route_kind", "TEXT"), ("route_name", "TEXT"), ("route_layer", "INTEGER")):
        try:
            conn.execute(f"ALTER TABLE exposures ADD COLUMN {column} {kind}")
        except sqlite3.OperationalError as exc:
            if "duplicate column" not in str(exc).lower():
                raise
    set_schema_version(conn, 8)


def migrate_005_reserved_for_channels(conn):
    """Number 5 belongs to the channels branch (migrate_005_channels), which has already run on some
    databases. This slot is deliberately empty here and is never recorded as applied, so that branch's
    migration still runs on a database that skipped it. When the two branches are merged, replace this
    function with the real migration 005."""
    raise RuntimeError("migration 005 is reserved and must never run")


migrate_005_reserved_for_channels.reserved = True


def migrate_009_project_languages(conn):
    """Add explicit policy and version-bound language evidence; infer no legacy values."""
    legacy_project_columns = {row[1] for row in conn.execute('PRAGMA table_info(projects)')}
    for table, column, kind in (
            ('projects', 'discipline', 'TEXT'),
            ('projects', 'allowed_languages', "TEXT NOT NULL DEFAULT '[]'"),
            ('projects', 'language_policy_revision', 'INTEGER NOT NULL DEFAULT 0'),
            ('papers', 'metadata_language', 'TEXT'),
            ('papers', 'metadata_language_source', 'TEXT'),
            ('fulltext', 'source_pdf_sha256', 'TEXT')):
        # Some shipped v8 libraries already have a discipline field. Keep its
        # original values; revision 0 still requires an explicit language choice.
        if table == 'projects' and column == 'discipline' and column in legacy_project_columns:
            continue
        conn.execute(f'ALTER TABLE {table} ADD COLUMN {column} {kind}')
    conn.execute('''CREATE TABLE fulltext_languages (
        paper_key TEXT NOT NULL REFERENCES papers(key),
        pdf_sha256 TEXT NOT NULL,
        language TEXT NOT NULL,
        method TEXT NOT NULL,
        verified_at TEXT NOT NULL,
        PRIMARY KEY (paper_key, pdf_sha256)
    )''')
    set_schema_version(conn, 9)

MIGRATIONS = [
    migrate_001_multi_project,
    migrate_002_shared_papers,
    migrate_003_project_guidance,
    migrate_004_project_scoped_qa,
    migrate_005_reserved_for_channels,
    migrate_006_pdf_acquisition,
    migrate_007_pdf_versions,
    migrate_008_exposure_route,
    migrate_009_project_languages,
]


def _number(migration):
    return int(migration.__name__.split("_")[1])


def applied_versions(conn):
    """Every migration number recorded as applied (not just the highest: branches can number differently)."""
    try:
        return {int(row[0]) for row in conn.execute("SELECT version FROM schema_version")}
    except sqlite3.OperationalError:
        return set()


def _to_run(conn):
    applied = applied_versions(conn)
    return [m for m in MIGRATIONS if not getattr(m, "reserved", False) and _number(m) not in applied]


def pending(conn):
    return len(_to_run(conn))


def apply_migrations(conn):
    """Apply every migration whose number is not recorded yet, each one atomically.

    A migration that fails rolls back completely (DDL included) and the error propagates, so a
    half-applied schema is never recorded and the next start retries from a clean state.
    """
    current_version = get_schema_version(conn)
    for migration in _to_run(conn):
        number = _number(migration)
        _log(f"Applying migration {number}: {migration.__name__}")
        conn.commit()
        conn.execute("BEGIN")
        try:
            migration(conn)
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        _log(f"Migration {number} applied successfully")

    final_version = get_schema_version(conn)
    if final_version == current_version:
        _log(f"Database is up to date (version {final_version})")
    else:
        _log(f"Database migrated from version {current_version} to {final_version}")

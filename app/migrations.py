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

    # Create default project for existing data
    default_project_id = "default_project"
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


def migrate_005_channels(conn):
    """Multi-channel papers (ADR 0010): identity columns, per-channel provenance, per-project channels."""
    from app.channels import dedup
    from app.channels.presets import DEFAULT, LEGACY_CHANNELS
    for column, kind in (("language", "TEXT"), ("url", "TEXT"), ("pdf_url", "TEXT"), ("channel", "TEXT"),
                         ("authors", "TEXT"), ("title_norm", "TEXT"), ("year", "INTEGER")):
        try:
            conn.execute(f"ALTER TABLE papers ADD COLUMN {column} {kind}")
        except sqlite3.OperationalError:
            pass  # column already exists
    conn.execute("""CREATE TABLE IF NOT EXISTS paper_ids (
        scheme TEXT NOT NULL, value TEXT NOT NULL,
        paper_key TEXT NOT NULL REFERENCES papers(key) ON DELETE CASCADE,
        PRIMARY KEY (scheme, value))""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_paper_ids_paper ON paper_ids(paper_key)")
    conn.execute("""CREATE TABLE IF NOT EXISTS paper_sources (
        paper_key TEXT NOT NULL REFERENCES papers(key) ON DELETE CASCADE,
        channel TEXT NOT NULL, query TEXT, found_at TEXT NOT NULL,
        PRIMARY KEY (paper_key, channel))""")
    try:
        conn.execute("ALTER TABLE projects ADD COLUMN discipline TEXT NOT NULL DEFAULT 'cs_ai'")
    except sqlite3.OperationalError:
        pass
    conn.execute("""CREATE TABLE IF NOT EXISTS project_channels (
        project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        channel TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1,
        auto_search INTEGER NOT NULL DEFAULT 0, query_override TEXT,
        PRIMARY KEY (project_id, channel))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS channel_usage (
        channel TEXT NOT NULL, day TEXT NOT NULL, requests INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (channel, day))""")
    # Holds no secret: only the state the settings page shows (configured / expired / last check).
    conn.execute("""CREATE TABLE IF NOT EXISTS channel_status (
        channel TEXT PRIMARY KEY, state TEXT NOT NULL, detail TEXT, checked_at TEXT NOT NULL)""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_papers_title_year ON papers(title_norm, year)")
    # Backfill: every earlier paper came from OpenAlex or an import of OpenAlex data.
    for row in conn.execute("SELECT key, openalex_id, doi, arxiv_id, title, published FROM papers").fetchall():
        paper = dict(row)
        conn.execute("UPDATE papers SET title_norm=?, year=?, channel=COALESCE(channel, ?) WHERE key=?",
                     (dedup.title_key(paper["title"]), dedup.year_of(paper["published"]),
                      "openalex" if paper["openalex_id"] else None, paper["key"]))
        for scheme, value in dedup.paper_ids(paper):
            conn.execute("INSERT OR IGNORE INTO paper_ids(scheme, value, paper_key) VALUES (?,?,?)",
                         (scheme, value, paper["key"]))
        conn.execute("""INSERT OR IGNORE INTO paper_sources(paper_key, channel, query, found_at)
                        SELECT key, 'openalex', NULL, created_at FROM papers WHERE key=? AND openalex_id IS NOT NULL""",
                     (paper["key"],))
    for row in conn.execute("SELECT id FROM projects").fetchall():
        for channel in LEGACY_CHANNELS:
            conn.execute("INSERT OR IGNORE INTO project_channels(project_id, channel) VALUES (?,?)",
                         (row["id"], channel))
    set_schema_version(conn, 5)


MIGRATIONS = [
    migrate_001_multi_project,
    migrate_002_shared_papers,
    migrate_003_project_guidance,
    migrate_004_project_scoped_qa,
    migrate_005_channels,
]


def pending(conn):
    return len(MIGRATIONS) - get_schema_version(conn)


def apply_migrations(conn):
    """Apply all pending migrations in order."""
    current_version = get_schema_version(conn)

    for i, migration in enumerate(MIGRATIONS, start=1):
        if i > current_version:
            _log(f"Applying migration {i}: {migration.__name__}")
            migration(conn)
            conn.commit()
            _log(f"Migration {i} applied successfully")

    final_version = get_schema_version(conn)
    if final_version == current_version:
        _log(f"Database is up to date (version {final_version})")
    else:
        _log(f"Database migrated from version {current_version} to {final_version}")

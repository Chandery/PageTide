"""Database migrations for multi-project support.

Each migration is a function that takes a connection and applies schema changes.
Migrations are tracked in a new `schema_version` table.
"""
import json
import sqlite3


def now():
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def get_schema_version(conn):
    """Get current schema version, or 0 if not tracked yet."""
    try:
        row = conn.execute("SELECT version FROM schema_version ORDER BY applied_at DESC LIMIT 1").fetchone()
        return row[0] if row else 0
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


MIGRATIONS = [
    migrate_001_multi_project,
]


def apply_migrations(conn):
    """Apply all pending migrations in order."""
    current_version = get_schema_version(conn)

    for i, migration in enumerate(MIGRATIONS, start=1):
        if i > current_version:
            print(f"Applying migration {i}: {migration.__name__}")
            migration(conn)
            conn.commit()
            print(f"Migration {i} applied successfully")

    final_version = get_schema_version(conn)
    if final_version == current_version:
        print(f"Database is up to date (version {final_version})")
    else:
        print(f"Database migrated from version {current_version} to {final_version}")

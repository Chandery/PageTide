"""Project management: CRUD operations for research projects.

Each project has independent profile, recommendations, and paper library.
"""
import json
import uuid


def now():
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


class ProjectManager:
    def __init__(self, store):
        self.store = store

    def create_project(self, name, creation_mode="manual", keywords=None,
                      guidance_transcript=None, learning_path=None):
        """Create a new research project.

        Args:
            name: Project display name
            creation_mode: 'quick', 'manual', or 'ai_guided'
            keywords: List of initial keywords (optional)
            guidance_transcript: AI conversation history for ai_guided mode
            learning_path: Recommended learning path for ai_guided mode

        Returns:
            project_id: UUID string
        """
        if creation_mode not in {"quick", "manual", "ai_guided"}:
            raise ValueError("invalid creation mode")
        name = str(name or "").strip()
        if not name or len(name) > 120:
            raise ValueError("项目名称不能为空且不能超过 120 个字符")
        project_id = str(uuid.uuid4())

        self.store.conn.execute("""
            INSERT INTO projects
            (id, name, creation_mode, creation_timestamp, keywords,
             guidance_transcript, recommended_learning_path)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            project_id,
            name,
            creation_mode,
            now(),
            json.dumps(keywords or [], ensure_ascii=False),
            json.dumps(guidance_transcript or [], ensure_ascii=False) if guidance_transcript else None,
            json.dumps(learning_path or {}, ensure_ascii=False) if learning_path else None
        ))
        self.store.conn.commit()

        return project_id

    def get_project(self, project_id):
        """Get project by ID."""
        row = self.store.conn.execute(
            "SELECT * FROM projects WHERE id=?", (project_id,)
        ).fetchone()

        if not row:
            return None

        return {
            "id": row["id"],
            "name": row["name"],
            "creation_mode": row["creation_mode"],
            "creation_timestamp": row["creation_timestamp"],
            "keywords": json.loads(row["keywords"]) if row["keywords"] else [],
            "decay_window_days": row["decay_window_days"],
            "guidance_transcript": json.loads(row["guidance_transcript"]) if row["guidance_transcript"] else None,
            "recommended_learning_path": json.loads(row["recommended_learning_path"]) if row["recommended_learning_path"] else None
        }

    def list_projects(self):
        """List all projects ordered by creation time."""
        rows = self.store.conn.execute(
            "SELECT * FROM projects ORDER BY creation_timestamp DESC"
        ).fetchall()

        return [
            {
                "id": row["id"],
                "name": row["name"],
                "creation_mode": row["creation_mode"],
                "creation_timestamp": row["creation_timestamp"],
                "keywords": json.loads(row["keywords"]) if row["keywords"] else [],
                "decay_window_days": row["decay_window_days"]
            }
            for row in rows
        ]

    def update_project(self, project_id, name=None, keywords=None, decay_window_days=None):
        """Update project metadata."""
        updates = []
        params = []

        if name is not None:
            updates.append("name=?")
            params.append(name)
        if keywords is not None:
            updates.append("keywords=?")
            params.append(json.dumps(keywords, ensure_ascii=False))
        if decay_window_days is not None:
            updates.append("decay_window_days=?")
            params.append(decay_window_days)

        if not updates:
            return

        params.append(project_id)
        sql = f"UPDATE projects SET {', '.join(updates)} WHERE id=?"
        self.store.conn.execute(sql, params)
        self.store.conn.commit()

    def delete_project(self, project_id):
        """Delete one project's state while retaining canonical paper facts."""
        self.store.conn.execute("DELETE FROM project_library WHERE project_id=?", (project_id,))
        self.store.conn.execute("DELETE FROM project_papers WHERE project_id=?", (project_id,))
        self.store.conn.execute("DELETE FROM feedback WHERE project_id=?", (project_id,))
        self.store.conn.execute(
            "DELETE FROM exposures WHERE batch_id IN (SELECT id FROM batches WHERE project_id=?)", (project_id,))
        self.store.conn.execute("DELETE FROM batches WHERE project_id=?", (project_id,))
        self.store.conn.execute("DELETE FROM qa_history WHERE project_id=?", (project_id,))
        for row in self.store.conn.execute(
                "SELECT id, draft FROM project_guidance_sessions WHERE status='confirmed'").fetchall():
            try:
                if json.loads(row["draft"]).get("project_id") == project_id:
                    self.store.conn.execute("DELETE FROM project_guidance_sessions WHERE id=?", (row["id"],))
            except (TypeError, ValueError):
                continue
        self.store.conn.execute("DELETE FROM profile_snapshots WHERE project_id=?", (project_id,))
        self.store.conn.execute("DELETE FROM weekly_reports WHERE project_id=?", (project_id,))
        for row in self.store.conn.execute("SELECT id, data FROM profile_versions").fetchall():
            try:
                if json.loads(row["data"]).get("project_id") == project_id:
                    self.store.conn.execute("DELETE FROM profile_versions WHERE id=?", (row["id"],))
            except (TypeError, ValueError):
                continue
        # Legacy compatibility column may still point at the deleted project;
        # relationship rows above are now the authoritative ownership model.
        self.store.conn.execute("UPDATE papers SET project_id=NULL WHERE project_id=?", (project_id,))
        # The legacy global library is kept only while at least one project still
        # has the paper saved; canonical metadata/PDF/fulltext always remains.
        self.store.conn.execute("""
            DELETE FROM library WHERE paper_key NOT IN
            (SELECT paper_key FROM project_library)
        """)
        self.store.conn.execute("DELETE FROM projects WHERE id=?", (project_id,))
        self.store.conn.execute(
            "DELETE FROM settings WHERE key IN (?,?,?)",
            (f"seed_keys_{project_id}", f"profile_freeze_{project_id}", f"project_default_terms_{project_id}"))
        self.store.conn.commit()

    def get_project_stats(self, project_id):
        """Get statistics for a project."""
        paper_count = self.store.conn.execute(
            "SELECT COUNT(*) as cnt FROM project_papers WHERE project_id=?", (project_id,)
        ).fetchone()["cnt"]

        library_count = self.store.conn.execute("""
            SELECT COUNT(*) as cnt FROM project_library WHERE project_id=?
        """, (project_id,)).fetchone()["cnt"]

        feedback_count = self.store.conn.execute(
            "SELECT COUNT(*) as cnt FROM feedback WHERE project_id=? AND undone=0",
            (project_id,)
        ).fetchone()["cnt"]

        return {
            "paper_count": paper_count,
            "library_count": library_count,
            "feedback_count": feedback_count
        }

    def save_snapshot(self, project_id, top_keywords, interest_distribution):
        """Save a profile snapshot for a project."""
        self.store.conn.execute("""
            INSERT INTO profile_snapshots
            (project_id, snapshot_timestamp, top_keywords, interest_distribution)
            VALUES (?, ?, ?, ?)
        """, (
            project_id,
            now(),
            json.dumps(top_keywords, ensure_ascii=False),
            json.dumps(interest_distribution, ensure_ascii=False)
        ))
        self.store.conn.commit()

    def get_snapshots(self, project_id, limit=30):
        """Get recent profile snapshots for a project."""
        rows = self.store.conn.execute("""
            SELECT * FROM profile_snapshots
            WHERE project_id=?
            ORDER BY snapshot_timestamp DESC
            LIMIT ?
        """, (project_id, limit)).fetchall()

        return [
            {
                "id": row["id"],
                "timestamp": row["snapshot_timestamp"],
                "top_keywords": json.loads(row["top_keywords"]),
                "interest_distribution": json.loads(row["interest_distribution"])
            }
            for row in rows
        ]

    def save_weekly_report(self, project_id, week_start, week_end, stats,
                          keyword_changes=None, ai_analysis=None):
        """Save a weekly report for a project."""
        self.store.conn.execute("""
            INSERT INTO weekly_reports
            (project_id, week_start, week_end, stats, keyword_changes, ai_analysis, generated_timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            project_id,
            week_start,
            week_end,
            json.dumps(stats, ensure_ascii=False),
            json.dumps(keyword_changes, ensure_ascii=False) if keyword_changes else None,
            ai_analysis,
            now()
        ))
        self.store.conn.commit()

    def get_weekly_reports(self, project_id, limit=10):
        """Get recent weekly reports for a project."""
        rows = self.store.conn.execute("""
            SELECT * FROM weekly_reports
            WHERE project_id=?
            ORDER BY week_start DESC
            LIMIT ?
        """, (project_id, limit)).fetchall()

        return [
            {
                "id": row["id"],
                "week_start": row["week_start"],
                "week_end": row["week_end"],
                "stats": json.loads(row["stats"]),
                "keyword_changes": json.loads(row["keyword_changes"]) if row["keyword_changes"] else None,
                "ai_analysis": row["ai_analysis"],
                "generated_timestamp": row["generated_timestamp"]
            }
            for row in rows
        ]

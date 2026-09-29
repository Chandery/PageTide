"""Weekly report generation for multi-project support.

Generates weekly activity summaries showing feedback trends and keyword changes.
Zero-token by default: analyzes local data only. AI analysis is optional and
token-consuming.
"""
import json
from datetime import datetime, timedelta


def generate_weekly_report(project_id, service):
    """Generate a weekly report for a project.

    Args:
        project_id: Project ID to generate report for
        service: App instance with database access

    Returns:
        dict with stats, keyword_changes, and week_start/week_end timestamps
    """
    today = datetime.now()
    week_start = today - timedelta(days=7)

    # Get feedback from the past week
    conn = service.store.conn
    feedback_rows = conn.execute("""
        SELECT key, action, created_at FROM feedback
        WHERE project_id = ? AND created_at >= ?
        ORDER BY created_at DESC
    """, (project_id, week_start.isoformat())).fetchall()

    # Calculate stats
    stats = {
        "saved": 0,
        "negative": 0,
        "too_hard": 0,
        "total_saved": 0,
    }

    for row in feedback_rows:
        action = row[1]
        if action == "useful":
            stats["saved"] += 1
        elif action == "irrelevant":
            stats["negative"] += 1
        elif action == "too_hard":
            stats["too_hard"] += 1

    # Get total saved count
    total_saved_row = conn.execute("""
        SELECT COUNT(*) FROM feedback
        WHERE project_id = ? AND action = 'useful'
    """, (project_id,)).fetchone()
    stats["total_saved"] = total_saved_row[0] if total_saved_row else 0

    # Get current profile keywords for trending analysis
    profile = service.profile(project_id)
    current_keywords = profile.get("keywords", [])

    # Simplified keyword change detection
    # In a full implementation, this would compare with previous snapshots
    keyword_changes = {
        "rising": current_keywords[:3] if len(current_keywords) >= 3 else current_keywords,
        "stable": current_keywords[3:6] if len(current_keywords) > 3 else [],
        "falling": [],
    }

    return {
        "week_start": week_start.isoformat(),
        "week_end": today.isoformat(),
        "stats": stats,
        "keyword_changes": keyword_changes,
    }

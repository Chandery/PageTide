"""Daily request ceilings, reserved in SQLite before the request is made (ADR 0010).

The ceilings are provisional engineering limits, not owner-approved budgets. They bound how
hard the app hits a shared public service; they do not meter money.
"""
import datetime

from .http import SourceError


def today():
    return datetime.date.today().isoformat()


def reserve(conn, channel_id, cap, amount=1):
    """Take `amount` requests of today's allowance, or raise SourceError('quota_exhausted')."""
    day = today()
    conn.execute("INSERT OR IGNORE INTO channel_usage(channel, day, requests) VALUES (?,?,0)", (channel_id, day))
    cur = conn.execute(
        "UPDATE channel_usage SET requests=requests+? WHERE channel=? AND day=? AND requests+?<=?",
        (amount, channel_id, day, amount, cap))
    conn.commit()
    if cur.rowcount != 1:
        raise SourceError(f"{channel_id}: today's request ceiling ({cap}) is used up", "quota_exhausted")


def used(conn, channel_id):
    row = conn.execute("SELECT requests FROM channel_usage WHERE channel=? AND day=?",
                       (channel_id, today())).fetchone()
    return row[0] if row else 0

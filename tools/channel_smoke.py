#!/usr/bin/env python3
"""Live smoke test of every registered channel: one tiny query each, results written as sanitized evidence.

    python3 tools/channel_smoke.py                    # all channels, prints a table
    python3 tools/channel_smoke.py --only arxiv crossref --out docs/evidence/2026-10-01-channel-smoke.md

Needs network access to each channel's host and sends public search terms only ("world model",
"数字人文"); no project, profile or seed data. Credentials, when a channel needs one, are read by the app's
vault in later units and are never printed. A failure is recorded as a failure: the file says which
channel could not be reached, not that it works.
"""
import argparse
import datetime
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.channels import query, registry  # noqa: E402
from app.channels.base import Context  # noqa: E402
from app.channels.http import SourceError  # noqa: E402

TERMS = ["world model", "数字人文"]
SINCE = "2024-01-01"


def run_channel(channel, ctx, terms=TERMS, limit=3):
    """One row per (channel, term): status, count, first title, error kind."""
    rows = []
    for term in query.terms_for(channel, terms, limit=len(terms)):
        row = {"channel": channel.id, "term": term, "status": "ok", "count": 0, "first": "", "kind": ""}
        try:
            papers = channel.search(ctx, term, SINCE, limit)
            row["count"] = len(papers)
            row["first"] = papers[0]["title"][:80] if papers else ""
            if papers and not all(p.get("title") and p.get("key") for p in papers):
                row["status"] = "bad_shape"
        except SourceError as exc:
            row.update(status="error", kind=exc.kind)
        except Exception as exc:  # a parser bug must show up here, not abort the run
            row.update(status="error", kind=type(exc).__name__)
        rows.append(row)
    if not rows:
        rows.append({"channel": channel.id, "term": "", "status": "skipped", "count": 0, "first": "",
                     "kind": "no_matching_terms"})
    return rows


def render(rows, when):
    lines = [f"# Channel smoke {when}", "",
             "Live public queries, one per channel and script. `error` rows are failures, not passes.", "",
             "| channel | term | status | results | first title | error kind |", "|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['channel']} | {r['term']} | {r['status']} | {r['count']} | "
                     f"{r['first'].replace('|', '/')} | {r['kind']} |")
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--only", nargs="*", help="channel ids to run")
    parser.add_argument("--out", help="write the table to this file")
    args = parser.parse_args(argv)
    rows = []
    with tempfile.TemporaryDirectory() as cache:
        ctx = Context(cache_dir=Path(cache))
        for channel in registry.all_channels():
            if args.only and channel.id not in args.only:
                continue
            rows += run_channel(channel, ctx)
    text = render(rows, datetime.datetime.now().astimezone().replace(microsecond=0).isoformat())
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    print(text)
    return 0 if rows and all(r["status"] in ("ok", "skipped") for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())

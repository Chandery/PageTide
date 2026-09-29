#!/usr/bin/env python3
"""Headless CLI for the daily loop. Also useful for tests and automation.

Examples:
    python3 -m app.cli init
    python3 -m app.cli refresh --pages 1
    python3 -m app.cli daily --triage --dry-run
    python3 -m app.cli fb 1 useful
    python3 -m app.cli profile --pin "world model,latent planning"
"""
import argparse
import json
import sys

from .service import App


def _print_cards(cards, triage=None):
    summaries = {item.get("paper_id"): item for item in (triage or {}).get("items", [])}
    for card in cards:
        print(f"\n[{card['rank']}] {card['title']}")
        print(f"    {card['published']} · {card['source']} · {card['why']} · {card['mode']}")
        print(f"    {card['url']}")
        if card["abstract"]:
            print(f"    {card['abstract'][:280]}...")
        summary = summaries.get(card["key"])
        if summary:
            print(f"    AI: {summary.get('one_liner')} | 相关: {summary.get('why_relevant')} | 注意: {summary.get('caution')}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--dev", action="store_true", help="test mode: separate ledger and loose ceilings")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init")
    sub.add_parser("seeds")

    refresh = sub.add_parser("refresh")
    refresh.add_argument("--pages", type=int, default=1)
    refresh.add_argument("--per-page", type=int, default=100)
    refresh.add_argument("--from-date", default="2024-01-01")
    refresh.add_argument("--no-distractors", dest="distractors", action="store_false")

    daily = sub.add_parser("daily")
    daily.add_argument("--limit", type=int, default=5)
    daily.add_argument("--triage", action="store_true")
    daily.add_argument("--dry-run", action="store_true")

    sub.add_parser("cards")

    imp = sub.add_parser("import-candidates", help="load a frozen candidate JSON (offline/dev)")
    imp.add_argument("path")

    fb = sub.add_parser("fb")
    fb.add_argument("position", type=int, help="1-based position in the latest batch")
    fb.add_argument("action", choices=["useful", "irrelevant", "too_hard"])

    undo = sub.add_parser("undo")
    undo.add_argument("feedback_id", type=int)

    profile = sub.add_parser("profile")
    profile.add_argument("--pin", default=None, help="comma-separated terms to pin")

    pdf = sub.add_parser("pdf")
    pdf.add_argument("position", type=int)

    triage = sub.add_parser("triage")
    triage.add_argument("--dry-run", action="store_true")

    args = parser.parse_args(argv)
    if getattr(args, "dev", False):
        import os
        os.environ["PDH_DEV"] = "1"
    app = App(data_dir=args.data_dir)

    if args.command == "init":
        keys = app.ensure_seed_papers()
        print(f"initialised; profile at {app.data}; seeds resolved: {len(keys)}")
    elif args.command == "seeds":
        print(json.dumps(app.ensure_seed_papers(), ensure_ascii=False, indent=2))
    elif args.command == "refresh":
        print(json.dumps(app.refresh_candidates(pages=args.pages, per_page=args.per_page,
                                                 from_date=args.from_date,
                                                 include_distractors=args.distractors), ensure_ascii=False))
    elif args.command == "daily":
        result = app.build_batch(limit=args.limit)
        triage = app.triage(result["cards"], dry_run=args.dry_run) if (args.triage and result["cards"]) else None
        _print_cards(result["cards"], triage)
        if not result["cards"]:
            print(f"no cards: {result.get('reason')}")
        if triage:
            print(f"\ntriage: ok={triage.get('ok')} mode={triage.get('mode')} "
                  f"reason={triage.get('reason')} usd={triage.get('usd')} reservation={triage.get('reservation')}")
    elif args.command == "cards":
        _print_cards(app.cards())
    elif args.command == "import-candidates":
        print(json.dumps(app.import_candidates(args.path), ensure_ascii=False))
    elif args.command == "fb":
        cards = app.cards()
        if not 1 <= args.position <= len(cards):
            print(f"position out of range (1..{len(cards)})", file=sys.stderr)
            return 2
        print(json.dumps(app.record_feedback(cards[args.position - 1]["key"], args.action), ensure_ascii=False))
    elif args.command == "undo":
        print(json.dumps(app.undo_feedback(args.feedback_id), ensure_ascii=False))
    elif args.command == "profile":
        if args.pin is not None:
            data = app.store.current_profile() or {"project": "world-models", "weights": {"pos": 1.0, "neg": 0.5}}
            data["pinned_terms"] = [t.strip() for t in args.pin.split(",") if t.strip()]
            app.save_profile(data, note="pin")
        print(json.dumps(app.profile(), ensure_ascii=False, indent=2))
    elif args.command == "pdf":
        cards = app.cards()
        if not 1 <= args.position <= len(cards):
            print(f"position out of range (1..{len(cards)})", file=sys.stderr)
            return 2
        print(json.dumps(app.download_pdf(cards[args.position - 1]["key"]), ensure_ascii=False))
    elif args.command == "triage":
        print(json.dumps(app.triage(app.cards(), dry_run=args.dry_run), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

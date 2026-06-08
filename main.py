#!/usr/bin/env python3
import argparse
import sys
from collections import Counter

from models import CandidateStatus
from state import load_state, save_state, ensure_data_dir
from utils import parse_csv, setup_logging


def cmd_init(args):
    ensure_data_dir()
    candidates = parse_csv()
    save_state(candidates)
    print(f"Initialized {len(candidates)} candidates from CSV.")
    _print_status(candidates)


def cmd_status(args):
    candidates = load_state()
    if not candidates:
        print("No state file found. Run 'init' first.")
        return
    _print_status(candidates)


def _print_status(candidates):
    counts = Counter(c.status.value for c in candidates)
    print(f"\n{'Status':<25} {'Count':>5}")
    print("-" * 32)
    for status in CandidateStatus:
        count = counts.get(status.value, 0)
        if count > 0:
            print(f"  {status.value:<23} {count:>5}")
    print("-" * 32)
    print(f"  {'Total':<23} {len(candidates):>5}")
    print()


def cmd_extract(args):
    from steps.step1_extract import run_extract
    run_extract(limit=args.limit, headless=args.headless)


def cmd_analyze(args):
    from steps.step2_analyze import run_analyze
    run_analyze(limit=args.limit, headless=args.headless)


def cmd_score(args):
    from steps.step3_score import run_score
    run_score()


def cmd_connect(args):
    from steps.step4_connect import run_connect
    run_connect(limit=args.limit, headless=args.headless, dry_run=args.dry_run)


def cmd_followup(args):
    from steps.step5_followup import run_followup
    run_followup(limit=args.limit, headless=args.headless, dry_run=args.dry_run)


def cmd_export(args):
    from export_csv import run_export
    run_export()


def cmd_pipeline(args):
    """Run the full analysis pipeline: extract → analyze → score → export.
    Skips connection requests (do those manually).
    Audience analysis is separate (run audience_analyzer.py after)."""
    import logging
    log = logging.getLogger(__name__)

    print("=" * 60)
    print("PIPELINE: Extract → Analyze → Score → Export")
    print("=" * 60)

    # Step 1: Extract
    print("\n--- Step 1: Extract profiles from posts ---")
    from steps.step1_extract import run_extract
    run_extract(limit=args.limit, headless=args.headless)

    # Step 2: Analyze
    print("\n--- Step 2: Analyze profiles ---")
    from steps.step2_analyze import run_analyze
    run_analyze(limit=args.limit, headless=args.headless)

    # Step 3: Score
    print("\n--- Step 3: Score candidates ---")
    from steps.step3_score import run_score
    run_score()

    # Step 4: Export CSV
    print("\n--- Step 4: Export tracker CSV ---")
    from export_csv import run_export
    run_export()

    print("\n" + "=" * 60)
    print("PIPELINE COMPLETE")
    print("=" * 60)
    print("\nNext steps:")
    print("  1. Open data/campaign_tracker.csv to review")
    print("  2. Send connection requests manually on LinkedIn")
    print("  3. Run: python3 audience_analyzer.py --from-state")
    print("     (for audience ICP fitment on top candidates)")
    print("  4. Re-export: python3 main.py export")


def cmd_reanalyze(args):
    """Reset skipped/analyzed/failed candidates back to EXTRACTED so they can be re-scraped."""
    candidates = load_state()
    reset_statuses = {
        CandidateStatus.SKIPPED,
        CandidateStatus.ANALYZED,
        CandidateStatus.ANALYZE_FAILED,
        CandidateStatus.SCORED,
    }
    count = 0
    for c in candidates:
        if c.status in reset_statuses and c.profile_url:
            c.status = CandidateStatus.EXTRACTED
            c.headline = None
            c.current_company = None
            c.current_role = None
            c.location = None
            c.follower_count = None
            c.connection_count = None
            c.about_snippet = None
            c.recent_posts = []
            c.connection_status = None
            c.score = None
            c.score_breakdown = None
            c.is_icp = None
            c.score_reasoning = None
            count += 1
    save_state(candidates)
    print(f"Reset {count} candidates back to EXTRACTED. Run 'analyze' to re-scrape them.")


def cmd_skip(args):
    candidates = load_state()
    for c in candidates:
        if c.id == args.candidate_id:
            c.status = CandidateStatus.SKIPPED
            save_state(candidates)
            print(f"Marked {c.id} ({c.name or c.source_url}) as SKIPPED.")
            return
    print(f"Candidate {args.candidate_id} not found.")
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="LinkedIn Outreach Automator")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="Parse CSV and create initial state")
    sub.add_parser("status", help="Show candidate status summary")

    p_extract = sub.add_parser("extract", help="Step 1: Extract profiles from posts")
    p_extract.add_argument("--limit", type=int, default=None)
    p_extract.add_argument("--headless", action="store_true")

    p_analyze = sub.add_parser("analyze", help="Step 2: Analyze profiles")
    p_analyze.add_argument("--limit", type=int, default=None)
    p_analyze.add_argument("--headless", action="store_true")

    sub.add_parser("score", help="Step 3: Score and rank candidates")

    p_connect = sub.add_parser("connect", help="Step 4: Send connection requests")
    p_connect.add_argument("--limit", type=int, default=None)
    p_connect.add_argument("--headless", action="store_true")
    p_connect.add_argument("--dry-run", action="store_true")

    p_followup = sub.add_parser("followup", help="Step 5: Follow-up DMs")
    p_followup.add_argument("--limit", type=int, default=None)
    p_followup.add_argument("--headless", action="store_true")
    p_followup.add_argument("--dry-run", action="store_true")

    sub.add_parser("export", help="Export tracker CSV to data/campaign_tracker.csv")

    p_pipeline = sub.add_parser("pipeline", help="Run full pipeline: extract → analyze → score → export")
    p_pipeline.add_argument("--limit", type=int, default=None)
    p_pipeline.add_argument("--headless", action="store_true")

    sub.add_parser("reanalyze", help="Reset skipped/analyzed candidates for re-scraping")

    p_skip = sub.add_parser("skip", help="Mark a candidate as skipped")
    p_skip.add_argument("candidate_id")

    args = parser.parse_args()
    setup_logging(verbose=args.verbose)

    commands = {
        "init": cmd_init,
        "status": cmd_status,
        "extract": cmd_extract,
        "analyze": cmd_analyze,
        "score": cmd_score,
        "connect": cmd_connect,
        "followup": cmd_followup,
        "export": cmd_export,
        "pipeline": cmd_pipeline,
        "reanalyze": cmd_reanalyze,
        "skip": cmd_skip,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()

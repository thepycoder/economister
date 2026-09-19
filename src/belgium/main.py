#!/usr/bin/env python3
"""Belgium news pipeline CLI.

Typical usage:
    uv run python src/belgium/main.py
    uv run python src/belgium/main.py --stage ingest --days 7
    uv run python src/belgium/main.py --from-stage write --run-dir belgium_runs/2026-09-19
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow ``from belgium...`` when run as a script.
_SRC = Path(__file__).resolve().parent.parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from belgium.config import (  # noqa: E402
    DEFAULT_LOOKBACK_DAYS,
    DEFAULT_MAX_TOPICS,
    OPENROUTER_BELGIUM_MODEL,
)
from belgium.models import Shortlist  # noqa: E402
from belgium.pipeline import PipelineError, run_pipeline  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Belgium section pipeline: VRT ingest + OpenRouter agents",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s
  %(prog)s --days 7 --max-topics 5
  %(prog)s --to-stage curate
  %(prog)s --from-stage write --run-dir belgium_runs/2026-09-19
        """,
    )
    parser.add_argument(
        "--days",
        type=int,
        default=DEFAULT_LOOKBACK_DAYS,
        metavar="N",
        help=f"Look back N days of VRT coverage (default {DEFAULT_LOOKBACK_DAYS})",
    )
    parser.add_argument(
        "--max-topics",
        type=int,
        default=DEFAULT_MAX_TOPICS,
        metavar="N",
        help=f"Maximum topics to select (default {DEFAULT_MAX_TOPICS})",
    )
    parser.add_argument(
        "--stage",
        choices=("ingest", "curate", "write"),
        help="Run only this stage",
    )
    parser.add_argument(
        "--from-stage",
        choices=("ingest", "curate", "write"),
        help="Resume from this stage through the end",
    )
    parser.add_argument(
        "--to-stage",
        choices=("ingest", "curate", "write"),
        help="Stop after this stage (use --to-stage curate to shortlist only)",
    )
    parser.add_argument(
        "--run-dir",
        type=Path,
        help="Existing run directory (required for --from-stage / single stages after ingest)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help=f"OpenRouter model slug (default {OPENROUTER_BELGIUM_MODEL})",
    )
    parser.add_argument(
        "--no-bodies",
        action="store_true",
        help="Ingest titles/summaries only (skip full article fetch)",
    )
    return parser


def _print_shortlist(path: Path) -> None:
    """Print curated topics so they can be approved before writing."""
    data = Shortlist.load(path)
    if not data.topics:
        print("  Topics:    (none)")
        return
    print(f"  Topics:    {len(data.topics)}")
    if data.notes:
        print(f"  Notes:     {data.notes}")
    for i, topic in enumerate(data.topics, start=1):
        print(f"\n  {i}. {topic.working_hed}")
        print(f"     slug:       {topic.slug}")
        print(f"     confidence: {topic.confidence}")
        print(f"     why:        {topic.why_economist}")
        if topic.source_urls:
            print("     sources:")
            for url in topic.source_urls:
                print(f"       - {url}")


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.days <= 0:
        print("Error: --days must be positive", file=sys.stderr)
        return 1
    if args.max_topics <= 0:
        print("Error: --max-topics must be positive", file=sys.stderr)
        return 1

    print("\n" + "=" * 60)
    print("Belgium pipeline (VRT + OpenRouter)")
    print("=" * 60 + "\n")

    try:
        run_dir = run_pipeline(
            run_dir=args.run_dir,
            days=args.days,
            max_topics=args.max_topics,
            stage=args.stage,
            from_stage=args.from_stage,
            to_stage=args.to_stage,
            model=args.model,
            fetch_bodies=not args.no_bodies,
        )
    except PipelineError as exc:
        print(f"\nPipeline error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"\nUnexpected error: {exc}", file=sys.stderr)
        return 1

    print(f"\nDone. Run directory: {run_dir}")
    shortlist = run_dir / "shortlist.json"
    articles = run_dir / "articles"
    if shortlist.exists():
        print(f"  Shortlist: {shortlist}")
        _print_shortlist(shortlist)
    if articles.exists():
        files = sorted(articles.glob("*.json"))
        print(f"  Articles:  {len(files)} file(s) in {articles}")
        for md in sorted(articles.glob("*.md")):
            print(f"  Markdown:  {md}")
    run_state_path = run_dir / "run.json"
    if run_state_path.exists():
        import json
        from belgium.models import RunState

        state = RunState.load(run_state_path)
        total = (state.cost or {}).get("total_usd")
        if total is not None:
            note = ""
            if state.cost.get("is_byok"):
                note = " (BYOK upstream estimate)"
            print(f"  Cost:      ${total:.4f}{note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

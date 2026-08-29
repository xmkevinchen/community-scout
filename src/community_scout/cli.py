from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .runner import cleanup_run, default_runs_dir, inspect_run, resume_run, search_communities
from .sources import SOURCE_REGISTRY


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="community-scout",
        description="Create resumable file-based community discovery runs.",
    )
    parser.add_argument(
        "--runs-dir",
        type=Path,
        default=default_runs_dir(),
        help="Parent directory for temporary run workspaces",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    search_parser = subparsers.add_parser("search", help="Fetch sources into a new run workspace")
    search_parser.add_argument("query")
    search_parser.add_argument(
        "--source",
        action="append",
        choices=sorted(SOURCE_REGISTRY),
        help="Source to fetch; repeat for more than one. Defaults to all.",
    )
    search_parser.add_argument("--limit-per-source", type=int, default=100)
    search_parser.add_argument("--timeout", type=float, default=20.0)
    search_parser.add_argument("--json", action="store_true")

    resume_parser = subparsers.add_parser("resume", help="Retry incomplete sources in a run")
    resume_parser.add_argument("run_directory", type=Path)
    resume_parser.add_argument("--json", action="store_true")

    inspect_parser = subparsers.add_parser("inspect", help="Print a run's Agent handoff paths")
    inspect_parser.add_argument("run_directory", type=Path)
    inspect_parser.add_argument("--json", action="store_true")

    cleanup_parser = subparsers.add_parser("cleanup", help="Delete one explicit run workspace")
    cleanup_parser.add_argument("run_directory", type=Path)
    return parser


def _validate_positive(value: int, flag: str) -> None:
    if value < 1:
        raise ValueError(f"{flag} must be at least 1")


def _print_handoff(summary: dict[str, object], as_json: bool) -> None:
    if as_json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return
    print(f"status: {summary['status']}")
    print(f"run_directory: {summary['run_directory']}")
    print(f"manifest: {summary['manifest']}")
    print(f"candidates: {summary['candidates']}")
    print(f"report: {summary['report']}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "search":
            _validate_positive(args.limit_per_source, "--limit-per-source")
            selected = args.source or sorted(SOURCE_REGISTRY)
            handoff = search_communities(
                args.query,
                sources=selected,
                runs_dir=args.runs_dir,
                limit_per_source=args.limit_per_source,
                timeout=args.timeout,
            )
            _print_handoff(handoff, args.json)
            return 1 if handoff["status"] == "failed" else 0

        if args.command == "resume":
            handoff = resume_run(args.run_directory)
            _print_handoff(handoff, args.json)
            return 1 if handoff["status"] == "failed" else 0

        if args.command == "inspect":
            _print_handoff(inspect_run(args.run_directory), args.json)
            return 0

        if args.command == "cleanup":
            removed = cleanup_run(args.run_directory)
            print(f"removed: {removed}")
            return 0
    except ValueError as exc:
        parser.error(str(exc))
    return 2

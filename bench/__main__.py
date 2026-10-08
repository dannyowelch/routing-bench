"""CLI: python -m bench"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from bench.config import ROOT, load_dotenv, load_experiment, load_prices, load_tasks
from bench.runner import default_scratch_root, execute


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare Claude Code model-routing setups on cost per successful task."
    )
    parser.add_argument(
        "--setups",
        type=Path,
        default=ROOT / "setups.example.yaml",
        help="YAML file of setups (default: setups.example.yaml)",
    )
    parser.add_argument("--tasks-dir", type=Path, default=ROOT / "tasks")
    parser.add_argument("--prices", type=Path, default=ROOT / "prices.yaml")
    parser.add_argument("--out", type=Path, default=ROOT / "results" / "runs.jsonl")
    parser.add_argument(
        "--scratch-dir",
        type=Path,
        default=None,
        help="Where scratch workspaces go. Default is a fresh directory outside the repo.",
    )
    parser.add_argument("--claude", default="claude", help="Claude Code executable")
    parser.add_argument("--reps", type=int, default=1)
    parser.add_argument("--only", help="Comma-separated setup ids to run")
    parser.add_argument("--tasks", help="Comma-separated task ids to run")
    parser.add_argument(
        "--pilot",
        action="store_true",
        help="Run the first task on every setup, once. Ignores --tasks and forces --reps 1.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the claude commands and exit without calling a model.",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=Path(".env"),
        help="Optional env file to load. Existing environment variables win.",
    )
    args = parser.parse_args(argv)
    if args.reps < 1:
        parser.error("--reps must be >= 1")
    if args.pilot and args.tasks:
        parser.error("--pilot chooses the task; do not pass --tasks")
    if args.pilot and args.reps != 1:
        parser.error("--pilot runs one repetition; do not pass --reps")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    load_dotenv(args.env_file)
    experiment = load_experiment(args.setups)
    tasks = load_tasks(args.tasks_dir)
    prices = load_prices(args.prices)
    task_ids = None
    repeats = args.reps
    if args.pilot:
        tasks = tasks[:1]
        repeats = 1
        print(f"pilot: task {tasks[0].id} ({tasks[0].title}), every setup, 1 rep")
    elif args.tasks:
        task_ids = {item.strip() for item in args.tasks.split(",") if item.strip()}
    only = None
    if args.only:
        only = {item.strip() for item in args.only.split(",") if item.strip()}
    scratch = args.scratch_dir or default_scratch_root()
    if not args.dry_run:
        binary = args.claude
        if shutil.which(binary) is None and not Path(binary).exists():
            print(f"claude binary not found: {binary}", file=sys.stderr)
            print("Install Claude Code, or pass --claude. --dry-run does not need it.", file=sys.stderr)
            return 127
    print(f"scratch: {scratch}")
    return execute(
        experiment=experiment,
        tasks=tasks,
        prices=prices,
        out_path=args.out,
        scratch_root=scratch,
        claude_bin=args.claude,
        repeats=repeats,
        dry_run=args.dry_run,
        only=only,
        task_ids=task_ids,
    )


if __name__ == "__main__":
    raise SystemExit(main())

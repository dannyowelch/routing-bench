"""Summarize routing-benchmark JSONL.

Cost per passing task is the total computed cost for a setup divided by the
number of distinct tasks that passed at least once. Sample files with FAKE in
the name are example data, not measurements.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path


COLUMNS = [
    "setup",
    "runs",
    "pass_rate",
    "mean_cost_usd",
    "cost_per_passing_task_usd",
    "mean_latency_ms",
    "cache_hit_ratio",
    "consult_rate",
]


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            row = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"{path}:{line_number}: {exc}") from exc
        if not isinstance(row, dict):
            raise SystemExit(f"{path}:{line_number}: expected an object")
        rows.append(row)
    if not rows:
        raise SystemExit(f"{path} has no rows")
    return rows


def _num(value):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def summarize(rows: list[dict]) -> list[dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("arm") or "?")].append(row)
    summaries = []
    for setup, group in grouped.items():
        by_run: dict[str, list[dict]] = defaultdict(list)
        for row in group:
            by_run[str(row.get("run_id"))].append(row)
        runs = len(by_run)
        passed_runs = 0
        passing_tasks = set()
        consults = 0
        for run_rows in by_run.values():
            if run_rows and all(item.get("pass") is True for item in run_rows):
                passed_runs += 1
                passing_tasks.add(run_rows[0].get("task_id"))
            calls = [_num(item.get("advisor_calls")) for item in run_rows]
            calls = [value for value in calls if value is not None]
            if calls and max(calls) > 0:
                consults += 1
        missing_cost = 0
        total_cost = 0.0
        for row in group:
            cost = _num(row.get("cost_usd_computed"))
            if cost is None:
                missing_cost += 1
                cost = 0.0
            total_cost += cost
        walls = []
        for run_rows in by_run.values():
            wall = 0.0
            seen = False
            for row in run_rows:
                value = _num(row.get("wall_ms"))
                if value is None:
                    continue
                wall += value
                seen = True
            if seen:
                walls.append(wall)
        cache_read = 0.0
        cache_denom = 0.0
        for row in group:
            parts = [
                _num(row.get("input_uncached")),
                _num(row.get("cache_read")),
                _num(row.get("cache_write_5m")),
                _num(row.get("cache_write_1h")),
            ]
            if any(part is None for part in parts):
                continue
            uncached, read, write_5m, write_1h = parts
            cache_read += read
            cache_denom += uncached + read + write_5m + write_1h
        summaries.append(
            {
                "setup": setup,
                "runs": runs,
                "pass_rate": (passed_runs / runs) if runs else None,
                "mean_cost_usd": (total_cost / runs) if runs else None,
                "cost_per_passing_task_usd": (
                    total_cost / len(passing_tasks) if passing_tasks else None
                ),
                "mean_latency_ms": (sum(walls) / len(walls)) if walls else None,
                "cache_hit_ratio": (cache_read / cache_denom) if cache_denom else None,
                "consult_rate": (consults / runs) if runs else None,
                "missing_cost_rows": missing_cost,
                "passing_tasks": len(passing_tasks),
                "passes": passed_runs,
                "total_cost_usd": total_cost,
            }
        )
    return summaries


def _fmt(value, digits=4):
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def format_table(summaries: list[dict]) -> str:
    display = []
    for summary in summaries:
        display.append(
            {
                "setup": summary["setup"],
                "runs": str(summary["runs"]),
                "pass_rate": _fmt(summary["pass_rate"], 3),
                "mean_cost_usd": _fmt(summary["mean_cost_usd"], 6),
                "cost_per_passing_task_usd": _fmt(summary["cost_per_passing_task_usd"], 6),
                "mean_latency_ms": _fmt(summary["mean_latency_ms"], 1),
                "cache_hit_ratio": _fmt(summary["cache_hit_ratio"], 3),
                "consult_rate": _fmt(summary["consult_rate"], 3),
            }
        )
    widths = {column: len(column) for column in COLUMNS}
    for row in display:
        for column in COLUMNS:
            widths[column] = max(widths[column], len(row[column]))
    header = "  ".join(column.ljust(widths[column]) for column in COLUMNS)
    lines = [header, "  ".join("-" * widths[column] for column in COLUMNS)]
    for row in display:
        lines.append("  ".join(row[column].ljust(widths[column]) for column in COLUMNS))
    return "\n".join(lines)


def _csv_value(value):
    if isinstance(value, float):
        return f"{value:.8f}".rstrip("0").rstrip(".")
    return value


def write_csv(path: Path, summaries: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        for summary in summaries:
            writer.writerow({column: _csv_value(summary.get(column)) for column in COLUMNS})


def write_prom(path: Path, summaries: list[dict]) -> None:
    """Gauges for the local Grafana pass-rate panels. Not a Claude Code metric."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Fake or real, these gauges are produced by analyze.py from JSONL.",
        "# They are not Claude Code telemetry.",
    ]
    metrics = [
        ("benchmark_runs", "Benchmark runs for a setup", "runs"),
        ("benchmark_passes", "Runs whose hidden tests passed", "passes"),
        ("benchmark_passing_tasks", "Distinct tasks that passed at least once", "passing_tasks"),
        ("benchmark_cost_usd", "Sum of cost_usd_computed", "total_cost_usd"),
        ("benchmark_mean_latency_ms", "Mean run wall time in milliseconds", "mean_latency_ms"),
        ("benchmark_cache_hit_ratio", "cache_read / (uncached + cache_read + cache_write)", "cache_hit_ratio"),
    ]
    for name, help_text, key in metrics:
        lines.append(f"# HELP {name} {help_text}")
        lines.append(f"# TYPE {name} gauge")
        for summary in summaries:
            value = summary.get(key)
            if value is None:
                continue
            label = str(summary["setup"]).replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'{name}{{setup="{label}"}} {value}')
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def looks_fake(path: Path, rows: list[dict]) -> bool:
    if "FAKE" in path.name.upper():
        return True
    return all("FAKE" in str(row.get("notes") or "") for row in rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Summarize routing benchmark JSONL.")
    parser.add_argument("jsonl", type=Path)
    parser.add_argument("--csv", type=Path, help="Also write a CSV summary")
    parser.add_argument(
        "--prom",
        type=Path,
        help="Write Prometheus text for the Grafana pass-rate panels",
    )
    args = parser.parse_args(argv)
    rows = load_jsonl(args.jsonl)
    summaries = summarize(rows)
    if looks_fake(args.jsonl, rows):
        print("NOTE: FAKE example data, not a real benchmark result.")
    print(format_table(summaries))
    missing = sum(summary["missing_cost_rows"] for summary in summaries)
    if missing:
        print(f"warning: {missing} row(s) had no cost_usd_computed and were counted as 0")
    if args.csv:
        write_csv(args.csv, summaries)
        print(f"wrote {args.csv}")
    if args.prom:
        write_prom(args.prom, summaries)
        print(f"wrote {args.prom}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

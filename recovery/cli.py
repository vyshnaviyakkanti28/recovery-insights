"""Command-line entry point.

Usage:
    python -m recovery.cli path/to/export.xml
    python -m recovery.cli path/to/export.xml --days 30 --json
"""

from __future__ import annotations

import argparse
import json
import sys

from . import analyze, parse_export


def _fmt(value, suffix: str = "") -> str:
    return "-" if value is None else f"{value}{suffix}"


def _signed(value, suffix: str = "") -> str:
    return "not enough data" if value is None else f"{value:+}{suffix} per week"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Recovery insights from an Apple Health export.")
    parser.add_argument("export", help="Path to export.xml from the Health app")
    parser.add_argument("--days", type=int, default=14, help="How many recent days to show (default 14)")
    parser.add_argument("--json", action="store_true", help="Print the full result as JSON")
    args = parser.parse_args(argv)

    try:
        result = analyze(parse_export(args.export))
    except FileNotFoundError:
        print(f"File not found: {args.export}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, indent=2))
        return 0

    rows = result["days"][-args.days :]
    print(f"{'Date':<12}{'Sleep':>8}{'RHR':>8}{'HRV':>8}{'Steps':>9}{'Recovery':>10}")
    for row in rows:
        print(
            f"{row['day']:<12}"
            f"{_fmt(row['sleep_hours'], 'h'):>8}"
            f"{_fmt(row['resting_hr']):>8}"
            f"{_fmt(row['hrv_ms']):>8}"
            f"{_fmt(row['steps']):>9}"
            f"{_fmt(row['recovery_score']):>10}"
        )

    info = result["insights"]
    trend = info["weekly_trend"]
    print()
    print(f"Days analyzed:            {info['days_analyzed']}")
    print(f"Average recovery score:   {_fmt(info['average_recovery_score'])}")
    print(f"Sleep vs HRV (r):         {_fmt(info['sleep_to_hrv_correlation'])}")
    print(f"HRV trend:                {_signed(trend['hrv_ms'], ' ms')}")
    print(f"Resting HR trend:         {_signed(trend['resting_hr'], ' bpm')}")
    print(f"Sleep trend:              {_signed(trend['sleep_hours'], ' h')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

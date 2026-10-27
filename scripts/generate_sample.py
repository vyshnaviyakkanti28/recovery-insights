"""Generate a realistic synthetic Apple Health export for demos and tests.

The data is fake but behaves like the real thing: short nights are followed
by lower HRV and a higher resting heart rate the next day, so the analysis
has a genuine pattern to find.

Usage:
    python scripts/generate_sample.py --days 90 --out sample_export.xml
"""

from __future__ import annotations

import argparse
import random
from datetime import datetime, timedelta, timezone
from xml.sax.saxutils import quoteattr

TZ = timezone(timedelta(hours=-5))
FMT = "%Y-%m-%d %H:%M:%S %z"


def record(record_type: str, start: datetime, end: datetime, value) -> str:
    return (
        f"  <Record type={quoteattr(record_type)} sourceName=\"Sample Watch\" "
        f"startDate=\"{start.strftime(FMT)}\" endDate=\"{end.strftime(FMT)}\" "
        f"value={quoteattr(str(value))}/>\n"
    )


def generate(days: int, seed: int) -> str:
    rng = random.Random(seed)
    start_day = datetime(2026, 1, 1, tzinfo=TZ)
    parts = ['<?xml version="1.0" encoding="UTF-8"?>\n<HealthData locale="en_US">\n']

    for offset in range(days):
        day = start_day + timedelta(days=offset)

        # Last night's sleep, ending this morning.
        sleep_hours = max(4.5, min(9.5, rng.gauss(7.2, 0.8)))
        wake = day.replace(hour=7) + timedelta(minutes=rng.randint(-30, 30))
        bed = wake - timedelta(hours=sleep_hours)
        stage_start = bed
        for stage, share in (("Core", 0.55), ("Deep", 0.2), ("REM", 0.25)):
            stage_end = stage_start + timedelta(hours=sleep_hours * share)
            parts.append(record("HKCategoryTypeIdentifierSleepAnalysis", stage_start, stage_end,
                                f"HKCategoryValueSleepAnalysisAsleep{stage}"))
            stage_start = stage_end

        # Sleep debt pushes HRV down and resting heart rate up.
        sleep_effect = sleep_hours - 7.2
        hrv = rng.gauss(55 + 6 * sleep_effect, 4)
        rhr = rng.gauss(58 - 1.5 * sleep_effect, 1.5)

        for hour in (8, 14, 22):
            moment = day.replace(hour=hour)
            parts.append(record("HKQuantityTypeIdentifierHeartRateVariabilitySDNN", moment, moment,
                                round(hrv + rng.gauss(0, 3), 1)))
        parts.append(record("HKQuantityTypeIdentifierRestingHeartRate", day.replace(hour=9),
                            day.replace(hour=9), round(rhr, 1)))

        for hour in range(9, 21, 3):
            moment = day.replace(hour=hour)
            parts.append(record("HKQuantityTypeIdentifierStepCount", moment,
                                moment + timedelta(hours=1), rng.randint(500, 3500)))

    parts.append("</HealthData>\n")
    return "".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--out", default="sample_export.xml")
    args = parser.parse_args()
    with open(args.out, "w", encoding="utf-8") as handle:
        handle.write(generate(args.days, args.seed))
    print(f"Wrote {args.days} days of sample data to {args.out}")


if __name__ == "__main__":
    main()

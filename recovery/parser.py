"""Streaming parser for Apple Health `export.xml` files.

Apple Health exports can be several gigabytes, so the file is read with
`iterparse` and each element is cleared after use. Memory stays flat no
matter how large the export is.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import IO, Iterable
import xml.etree.ElementTree as ET

RESTING_HR = "HKQuantityTypeIdentifierRestingHeartRate"
HRV_SDNN = "HKQuantityTypeIdentifierHeartRateVariabilitySDNN"
STEP_COUNT = "HKQuantityTypeIdentifierStepCount"
SLEEP = "HKCategoryTypeIdentifierSleepAnalysis"

# Apple has used several values for "asleep" over the years. "InBed" and
# "Awake" are deliberately excluded so only real sleep time is counted.
ASLEEP_VALUES = {
    "HKCategoryValueSleepAnalysisAsleep",
    "HKCategoryValueSleepAnalysisAsleepUnspecified",
    "HKCategoryValueSleepAnalysisAsleepCore",
    "HKCategoryValueSleepAnalysisAsleepDeep",
    "HKCategoryValueSleepAnalysisAsleepREM",
}

DATE_FORMAT = "%Y-%m-%d %H:%M:%S %z"


@dataclass
class DailyRaw:
    """Raw per-day accumulators, before averaging."""

    sleep_seconds: float = 0.0
    resting_hr: list[float] = field(default_factory=list)
    hrv: list[float] = field(default_factory=list)
    steps: float = 0.0
    has_steps: bool = False


def parse_timestamp(value: str) -> datetime:
    return datetime.strptime(value, DATE_FORMAT)


def parse_export(source: str | Path | IO[bytes]) -> dict[date, DailyRaw]:
    """Parse an export and return raw values grouped by calendar day.

    Days use the timestamp's own local date, so a run recorded at 11 PM in
    the user's time zone stays on that day. Sleep is credited to the day you
    wake up, which matches how people think about "last night's sleep".
    """
    days: dict[date, DailyRaw] = defaultdict(DailyRaw)

    for _, elem in ET.iterparse(source, events=("end",)):
        if elem.tag != "Record":
            # Only clear finished top-level children, never the root.
            if elem.tag != "HealthData":
                elem.clear()
            continue

        record_type = elem.get("type")
        try:
            _apply_record(days, record_type, elem)
        except (TypeError, ValueError):
            # One malformed record should not fail a multi-year export.
            pass
        finally:
            elem.clear()

    return dict(days)


def _apply_record(days: dict[date, DailyRaw], record_type: str | None, elem: ET.Element) -> None:
    if record_type == SLEEP:
        if elem.get("value") not in ASLEEP_VALUES:
            return
        start = parse_timestamp(elem.get("startDate"))
        end = parse_timestamp(elem.get("endDate"))
        seconds = (end - start).total_seconds()
        if seconds > 0:
            days[end.date()].sleep_seconds += seconds
        return

    if record_type not in (RESTING_HR, HRV_SDNN, STEP_COUNT):
        return

    day = parse_timestamp(elem.get("startDate")).date()
    value = float(elem.get("value"))

    if record_type == RESTING_HR:
        days[day].resting_hr.append(value)
    elif record_type == HRV_SDNN:
        days[day].hrv.append(value)
    else:
        days[day].steps += value
        days[day].has_steps = True


def iter_sorted(days: dict[date, DailyRaw]) -> Iterable[tuple[date, DailyRaw]]:
    return sorted(days.items(), key=lambda item: item[0])

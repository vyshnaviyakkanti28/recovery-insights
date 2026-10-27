"""Tests for parsing and scoring. Run with `pytest` or `python -m unittest`."""

from __future__ import annotations

import io
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from generate_sample import generate  # noqa: E402
from recovery import analyze, parse_export  # noqa: E402
from recovery.metrics import (  # noqa: E402
    DailySummary,
    recovery_score,
    sleep_hrv_correlation,
    z_score,
)

SMALL_EXPORT = b"""<?xml version="1.0" encoding="UTF-8"?>
<HealthData locale="en_US">
  <Record type="HKCategoryTypeIdentifierSleepAnalysis" startDate="2026-03-01 23:00:00 -0500" endDate="2026-03-02 03:00:00 -0500" value="HKCategoryValueSleepAnalysisAsleepCore"/>
  <Record type="HKCategoryTypeIdentifierSleepAnalysis" startDate="2026-03-02 03:00:00 -0500" endDate="2026-03-02 06:30:00 -0500" value="HKCategoryValueSleepAnalysisAsleepREM"/>
  <Record type="HKCategoryTypeIdentifierSleepAnalysis" startDate="2026-03-01 22:30:00 -0500" endDate="2026-03-01 23:00:00 -0500" value="HKCategoryValueSleepAnalysisInBed"/>
  <Record type="HKQuantityTypeIdentifierHeartRateVariabilitySDNN" startDate="2026-03-02 08:00:00 -0500" endDate="2026-03-02 08:00:00 -0500" value="50"/>
  <Record type="HKQuantityTypeIdentifierHeartRateVariabilitySDNN" startDate="2026-03-02 20:00:00 -0500" endDate="2026-03-02 20:00:00 -0500" value="60"/>
  <Record type="HKQuantityTypeIdentifierRestingHeartRate" startDate="2026-03-02 09:00:00 -0500" endDate="2026-03-02 09:00:00 -0500" value="57"/>
  <Record type="HKQuantityTypeIdentifierStepCount" startDate="2026-03-02 10:00:00 -0500" endDate="2026-03-02 11:00:00 -0500" value="1200"/>
  <Record type="HKQuantityTypeIdentifierStepCount" startDate="2026-03-02 15:00:00 -0500" endDate="2026-03-02 16:00:00 -0500" value="800"/>
  <Record type="HKQuantityTypeIdentifierHeartRateVariabilitySDNN" startDate="not a date" endDate="not a date" value="40"/>
  <Record type="HKQuantityTypeIdentifierBodyMass" startDate="2026-03-02 07:00:00 -0500" endDate="2026-03-02 07:00:00 -0500" value="70"/>
</HealthData>
"""


def make_days(n: int, **overrides) -> list[DailySummary]:
    start = date(2026, 1, 1)
    days = []
    for i in range(n):
        values = {"sleep_hours": 7.0 + (i % 3) * 0.5, "resting_hr": 58.0 + (i % 2), "hrv_ms": 50.0 + (i % 4) * 2}
        days.append(DailySummary(day=start + timedelta(days=i), steps=8000, **values))
    for key, value in overrides.items():
        setattr(days[-1], key, value)
    return days


class ParserTests(unittest.TestCase):
    def setUp(self):
        self.days = parse_export(io.BytesIO(SMALL_EXPORT))
        self.day = self.days[date(2026, 3, 2)]

    def test_sleep_counts_asleep_stages_and_ignores_in_bed(self):
        self.assertAlmostEqual(self.day.sleep_seconds / 3600, 7.5)

    def test_sleep_is_credited_to_wake_up_day(self):
        self.assertNotIn(date(2026, 3, 1), self.days)

    def test_hrv_readings_are_collected(self):
        self.assertEqual(self.day.hrv, [50.0, 60.0])

    def test_steps_are_summed(self):
        self.assertEqual(self.day.steps, 2000)

    def test_malformed_and_unknown_records_are_skipped(self):
        self.assertEqual(len(self.days), 1)


class ScoringTests(unittest.TestCase):
    def test_z_score_needs_minimum_history(self):
        self.assertIsNone(z_score(10, [1, 2, 3]))

    def test_z_score_handles_flat_history(self):
        self.assertIsNone(z_score(10, [5.0] * 10))

    def test_z_score_value(self):
        self.assertAlmostEqual(z_score(14, [8, 10, 12, 10, 8, 12, 10]), 2.4495, places=3)

    def test_first_days_have_no_score(self):
        days = make_days(5)
        self.assertIsNone(recovery_score(days, 4))

    def test_typical_day_scores_near_50(self):
        days = make_days(30, hrv_ms=53.0, resting_hr=58.5, sleep_hours=7.5)
        self.assertTrue(35 <= recovery_score(days, 29) <= 65)

    def test_high_hrv_beats_low_hrv(self):
        good = make_days(30, hrv_ms=70.0)
        bad = make_days(30, hrv_ms=35.0)
        self.assertGreater(recovery_score(good, 29), recovery_score(bad, 29))

    def test_high_resting_heart_rate_lowers_score(self):
        calm = make_days(30, resting_hr=55.0)
        stressed = make_days(30, resting_hr=68.0)
        self.assertGreater(recovery_score(calm, 29), recovery_score(stressed, 29))

    def test_score_works_with_missing_metrics(self):
        days = make_days(30, hrv_ms=None, sleep_hours=None)
        self.assertIsNotNone(recovery_score(days, 29))

    def test_score_is_bounded(self):
        days = make_days(30, hrv_ms=500.0, resting_hr=30.0, sleep_hours=12.0)
        self.assertLessEqual(recovery_score(days, 29), 100)


class InsightTests(unittest.TestCase):
    def test_correlation_needs_enough_complete_days(self):
        days = [
            DailySummary(date(2026, 1, 1), 6.0, 60, 40, None),
            DailySummary(date(2026, 1, 2), 8.0, 58, None, None),
            DailySummary(date(2026, 1, 3), None, 59, 70, None),
        ]
        # Only one day has both sleep and HRV, which is not enough.
        self.assertIsNone(sleep_hrv_correlation(days))

    def test_correlation_detects_positive_relationship(self):
        days = [DailySummary(date(2026, 1, 1) + timedelta(days=i), 6.0 + i * 0.5, 60, 40.0 + i * 3, None)
                for i in range(5)]
        self.assertEqual(sleep_hrv_correlation(days), 1.0)

    def test_end_to_end_finds_sleep_hrv_relationship(self):
        result = analyze(parse_export(io.BytesIO(generate(days=90, seed=7).encode())))
        info = result["insights"]
        self.assertEqual(info["days_analyzed"], 90)
        # The sample generator links short nights to lower HRV, so a clear
        # positive correlation should come back out of the analysis.
        self.assertGreater(info["sleep_to_hrv_correlation"], 0.5)
        self.assertIsNotNone(info["average_recovery_score"])


if __name__ == "__main__":
    unittest.main()

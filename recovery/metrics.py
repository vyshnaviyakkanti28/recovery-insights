"""Daily summaries, personal baselines, and a recovery score.

The recovery score compares each day against the user's own recent history
rather than population averages. A resting heart rate of 60 bpm is great for
one person and a warning sign for another, so every metric is converted to a
z-score against a rolling personal baseline before it is combined.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, timedelta
from statistics import NormalDist, StatisticsError, correlation, fmean, linear_regression, stdev
from typing import Optional

from .parser import DailyRaw, iter_sorted

# How much each signal contributes to the composite score. HRV carries the
# most weight because it responds fastest to stress, illness, and training load.
WEIGHTS = {"hrv_ms": 0.5, "resting_hr": 0.3, "sleep_hours": 0.2}

# Higher HRV and more sleep are good; a higher resting heart rate is not.
DIRECTION = {"hrv_ms": 1.0, "resting_hr": -1.0, "sleep_hours": 1.0}

BASELINE_WINDOW_DAYS = 28
MIN_BASELINE_DAYS = 7

_STANDARD_NORMAL = NormalDist()


@dataclass
class DailySummary:
    day: date
    sleep_hours: Optional[float]
    resting_hr: Optional[float]
    hrv_ms: Optional[float]
    steps: Optional[int]
    recovery_score: Optional[int] = None

    def to_dict(self) -> dict:
        data = asdict(self)
        data["day"] = self.day.isoformat()
        return data


def summarize(days: dict[date, DailyRaw]) -> list[DailySummary]:
    """Collapse raw records into one summary per day, oldest first."""
    summaries = []
    for day, raw in iter_sorted(days):
        summaries.append(
            DailySummary(
                day=day,
                sleep_hours=round(raw.sleep_seconds / 3600, 2) if raw.sleep_seconds else None,
                resting_hr=round(fmean(raw.resting_hr), 1) if raw.resting_hr else None,
                hrv_ms=round(fmean(raw.hrv), 1) if raw.hrv else None,
                steps=int(raw.steps) if raw.has_steps else None,
            )
        )
    return summaries


def z_score(value: float, history: list[float]) -> Optional[float]:
    """How unusual `value` is compared to `history`, in standard deviations.

    Returns None when there is not enough history to judge, or when the
    history has no spread at all (dividing by zero would be meaningless).
    """
    if len(history) < MIN_BASELINE_DAYS:
        return None
    spread = stdev(history)
    if spread == 0:
        return None
    return (value - fmean(history)) / spread


def baseline_history(summaries: list[DailySummary], index: int, metric: str) -> list[float]:
    """Values of `metric` from the previous BASELINE_WINDOW_DAYS calendar days.

    Uses calendar days, not list positions, so gaps in the data (a week
    without the watch) do not stretch the window into older history.
    """
    today = summaries[index].day
    earliest = today - timedelta(days=BASELINE_WINDOW_DAYS)
    values = []
    for previous in reversed(summaries[:index]):
        if previous.day < earliest:
            break
        value = getattr(previous, metric)
        if value is not None:
            values.append(value)
    return values


def recovery_score(summaries: list[DailySummary], index: int) -> Optional[int]:
    """Score one day from 0 to 100, where 50 means a typical day for this user.

    Each available metric becomes a direction-adjusted z-score. The z-scores
    are averaged using WEIGHTS, renormalized over the metrics that exist that
    day, and mapped through the standard normal CDF so the result reads like
    a percentile of the user's own normal range.
    """
    day = summaries[index]
    weighted_sum = 0.0
    weight_total = 0.0

    for metric, weight in WEIGHTS.items():
        value = getattr(day, metric)
        if value is None:
            continue
        z = z_score(value, baseline_history(summaries, index, metric))
        if z is None:
            continue
        weighted_sum += weight * DIRECTION[metric] * z
        weight_total += weight

    if weight_total == 0:
        return None

    composite = weighted_sum / weight_total
    return round(100 * _STANDARD_NORMAL.cdf(composite))


def score_all(summaries: list[DailySummary]) -> list[DailySummary]:
    for index, summary in enumerate(summaries):
        summary.recovery_score = recovery_score(summaries, index)
    return summaries


def sleep_hrv_correlation(summaries: list[DailySummary]) -> Optional[float]:
    """Pearson correlation between last night's sleep and today's HRV.

    The parser credits sleep to the day you wake up, so a day's
    `sleep_hours` is the night before it. Comparing it with the same day's
    HRV therefore answers "does a short night lower my HRV the next day?"
    Only days that have both values are used.
    """
    pairs = [(s.sleep_hours, s.hrv_ms) for s in summaries if s.sleep_hours is not None and s.hrv_ms is not None]
    if len(pairs) < 3:
        return None
    sleep, hrv = zip(*pairs)
    try:
        return round(correlation(sleep, hrv), 2)
    except StatisticsError:
        return None


def trend_per_week(summaries: list[DailySummary], metric: str, last_days: int = 28) -> Optional[float]:
    """Least-squares slope of `metric` over the recent window, per week."""
    if not summaries:
        return None
    end = summaries[-1].day
    start = end - timedelta(days=last_days)
    xs, ys = [], []
    for summary in summaries:
        value = getattr(summary, metric)
        if summary.day >= start and value is not None:
            xs.append((summary.day - start).days)
            ys.append(value)
    if len(xs) < 3:
        return None
    try:
        slope, _ = linear_regression(xs, ys)
    except StatisticsError:
        return None
    return round(slope * 7, 2)


def insights(summaries: list[DailySummary]) -> dict:
    scored = [s.recovery_score for s in summaries if s.recovery_score is not None]
    return {
        "days_analyzed": len(summaries),
        "average_recovery_score": round(fmean(scored)) if scored else None,
        "sleep_to_hrv_correlation": sleep_hrv_correlation(summaries),
        "weekly_trend": {
            "hrv_ms": trend_per_week(summaries, "hrv_ms"),
            "resting_hr": trend_per_week(summaries, "resting_hr"),
            "sleep_hours": trend_per_week(summaries, "sleep_hours"),
        },
    }


def analyze(days: dict[date, DailyRaw]) -> dict:
    """Full pipeline: raw records in, scored days and insights out."""
    summaries = score_all(summarize(days))
    return {
        "insights": insights(summaries),
        "days": [s.to_dict() for s in summaries],
    }

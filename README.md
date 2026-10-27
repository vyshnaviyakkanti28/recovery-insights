# Recovery Insights

Turn an Apple Health export into a daily **recovery score** and personal trends, using sleep, resting heart rate, heart rate variability (HRV), and steps.

Most health metrics only mean something relative to *you*. A resting heart rate of 60 bpm is excellent for one person and a warning sign for another. So instead of comparing against population averages, this project builds a rolling personal baseline for each metric and scores every day against your own normal range.

## Example output

```
Date           Sleep     RHR     HRV    Steps  Recovery
2026-03-24     6.79h    58.7    50.5     4360        25
2026-03-25     7.79h    55.2    60.5     8466        83
2026-03-26     8.54h    57.2    63.4     9222        85

Days analyzed:            90
Average recovery score:   53
Sleep vs HRV (r):         0.76
HRV trend:                -0.05 ms per week
Resting HR trend:         -0.18 bpm per week
Sleep trend:              +0.11 h per week
```

## How the recovery score works

1. **Daily summaries.** Records are grouped by calendar day. HRV and resting heart rate are averaged, steps are summed, and sleep counts only real sleep stages (Core, Deep, REM), not time in bed. Sleep is credited to the day you wake up.
2. **Personal baseline.** For each metric, the previous 28 calendar days form a baseline. At least 7 days of history are required before a day gets a score.
3. **Z-scores.** Each metric becomes a z-score: how many standard deviations today sits from your baseline. Resting heart rate is flipped, since a lower value is better.
4. **Weighted composite.** The z-scores are combined with weights of HRV 0.5, resting heart rate 0.3, and sleep 0.2. If a metric is missing that day, the weights are renormalized over the ones that exist.
5. **Score from 0 to 100.** The composite is passed through the standard normal CDF, so 50 means a typical day for you, and 84 means about one standard deviation better than usual.

It also reports the Pearson correlation between last night's sleep and today's HRV, plus least-squares trends for the last 28 days.

## Getting started

Requires Python 3.10 or newer.

```bash
git clone https://github.com/vyshnaviyakkanti28/recovery-insights.git
cd recovery-insights
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### Try it with sample data

```bash
python scripts/generate_sample.py --days 90 --out sample_export.xml
python -m recovery.cli sample_export.xml
python -m recovery.cli sample_export.xml --json
```

The sample generator creates realistic synthetic data where short nights lower the next morning's HRV, so the analysis has a real pattern to find.

### Use your own data

On iPhone, open **Health**, tap your profile picture, then **Export All Health Data**. Unzip the file and run:

```bash
python -m recovery.cli apple_health_export/export.xml
```

### Run the API

```bash
uvicorn api.main:app --reload
```

Open http://127.0.0.1:8000/docs to upload a file from your browser, or use curl:

```bash
curl -F "file=@sample_export.xml" http://127.0.0.1:8000/analyze
```

| Endpoint | Method | Description |
| --- | --- | --- |
| `/health` | GET | Health check |
| `/analyze` | POST | Upload `export.xml` and get daily scores and insights as JSON |

### Run the tests

```bash
pytest
```

## Design decisions

- **Streaming parser.** Real exports can be several gigabytes. The parser uses `iterparse` and clears each element after reading it, so memory use stays flat regardless of file size. The API writes uploads to a temporary file instead of holding them in memory.
- **No dependencies in the core.** The analysis uses only Python's standard library (`statistics`, `xml.etree`), so it's easy to embed, test, and reason about. FastAPI is only used for the HTTP layer.
- **Calendar-day windows.** Baselines use calendar days, not "the last 28 rows," so a week without the watch doesn't stretch the baseline into older history.
- **Fault tolerance.** One malformed record is skipped instead of failing a multi-year export.

## Project structure

```
recovery/
  parser.py      Streaming Apple Health parser
  metrics.py     Daily summaries, baselines, scoring, insights
  cli.py         Command-line interface
api/
  main.py        FastAPI service
scripts/
  generate_sample.py   Synthetic data generator
tests/
  test_recovery.py     Parser, scoring, and end-to-end tests
```

## Ideas for next steps

- Factor training load from workouts into the recovery score
- Store daily results in PostgreSQL and serve history over time
- Add a TypeScript web dashboard to chart the trends
- Tune the weights using data from more users

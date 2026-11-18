# Testing and checking the results

## Setup on your own computer

```
pip install -r requirements-analysis.txt
```

To use real data, download a backup from OneDrive (`fyp-backups`), unzip it and put it at `data/bus.db`. Backups are gzipped, so on Windows use 7-Zip or `gunzip`.

## One command for everything

```
python scripts/run_pipeline.py --db data/bus.db
```

Stages run in order and it stops at the first failure.

| stage | what it checks |
| --- | --- |
| unit tests | the pytest suite in `tests/` |
| stored data quality | gaps in collection, failed polls, absurd delays in the database |
| live feed check | fetches the real feeds (needs `NTA_API_KEY`) and checks they look sane |
| arrival detection | the GPS method and the feed method find arrivals and roughly agree |
| accuracy against TFI | the model is not worse than TFI on days it was not trained on |
| fallback without TFI | estimates from history alone are within 10 minutes on the latest day |
| human review | how often you agreed with the detected arrival times |

Each stage ends as PASS, FAIL, SKIP (not enough data yet) or TFI FAULT. TFI FAULT means the live feed looked broken (unreachable, stale, absurd values). That is not counted as a failure of this project, rerun later. `python scripts/run_pipeline.py --sim` runs the same stages on simulated data and is what GitHub runs on every push.

## What the tests are based on

Most tests use `bus/simulate.py`, which makes buses with a known real arrival time. That gives positive cases (the answer is there and must be found) and negative cases (there is nothing to find, so nothing should be claimed):

- a bus passes the stop, the arrival must be found within a few seconds
- a bus passes 100 m away, a long GPS gap, a cancelled trip, a collector outage: no arrival must be reported
- delays that depend on hour and rain: the model must beat TFI
- delays that are pure noise: the model must not be called better
- stale, empty and nonsense feeds must be rejected
- TFI down or unhealthy: an estimate must still come out, marked as coming from history
- `tests/test_system.py` runs a fake TFI server, the real collector code, the database and the estimate, one after the other

## Checking by eye

```
python -m bus.review --horizon 30
```

Open http://127.0.0.1:8000. Each page shows one bus: the distance from the stop over time, the detected arrival (green), what TFI said (red) and what the model said (blue). Answer "looks right" or "looks wrong". Answers are saved in the `reviews` table and counted by the last pipeline stage.

## Other commands

```
python -m bus.evaluate --horizon 30 60           # accuracy table for the report
python -m bus.evaluate --truth feed              # use the feed method as the ground truth
python -m bus.model --horizon 30 --out data/model30.pkl
python -m bus.predict --stop 5029 --model data/model30.pkl
python -m bus.simulate data/sim.db --days 14     # fake data to try things on
```

`bus.predict` uses the live feed when it passes the health checks and falls back to past arrivals at the same time of day when it does not.

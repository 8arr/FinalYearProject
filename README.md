# Final Year Project

Predicting bus arrival times for the 41C in Swords (main stop 5029 Boroimhe Laurels). TFI already gives a "due" time, the aim is to beat it at 30 and 60 minutes ahead using time of day, weather and later traffic and user ratings.

## Layout

- `collector/` polls the NTA GTFS-R feeds every minute and the weather every 10 minutes, stores everything in SQLite (`data/bus.db`)
- `bus/` works out the real arrival times, compares a correction model against TFI, checks the feed, and has the history fallback and the review page
- `scripts/` stop finder, timetable loader, status, backup, data overview and the test pipeline
- `deploy/` systemd unit for the VM
- `docs/gcp-setup.md` setting up the VM

## Collector

```
pip install -r requirements.txt
export NTA_API_KEY=your-key
python -m collector.run
```

You get a key by registering at https://developer.nationaltransport.ie and subscribing to GTFS-R. To change the stops: `python scripts/find_stops.py --main 5029 --routes 41C --count 6`.

The feed gives delays, not clock times, so load the timetable once with `python scripts/load_schedule.py --db data/bus.db`.

Tables: `trip_updates`, `vehicle_positions`, `weather`, `polls` (every request, so gaps can be explained), and `schedule`.

Real arrival times are not stored, they are worked out afterwards from the GPS positions (closest approach to the stop).

## Tests

```
pip install -r requirements-analysis.txt
python -m pytest -q tests
python scripts/run_pipeline.py --sim
```

`run_pipeline.py` runs the stages in order and stops at the first failure: unit tests, stored data quality, live feed, arrival detection, accuracy against TFI, fallback, human review. `--sim` uses made up data where the right answers are known, without `--sim` it uses `data/bus.db` (`--db` for another file). If TFI itself is broken it says "TFI FAULT" instead of failing.

Looking at a database for the first time: `python scripts/data_overview.py --db data/bus.db`. To check cases by hand: `python -m bus.review --horizon 30`.

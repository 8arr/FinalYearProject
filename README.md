# Final Year Project

Bus arrival time prediction for the 41C in Swords, Co. Dublin. The idea is to take the "due" times TFI shows and try to make them more accurate using the live bus position, time of day, weather and later on traffic and user ratings.

## What is in here

- `scripts/find_stops.py` picks the stops to watch (5029 Boroimhe Laurels and the closest stops on the 41C) and writes `data/targets.json`
- `collector/` polls the NTA GTFS-Realtime feeds once a minute plus the weather every 10 minutes and stores it all in SQLite (`data/bus.db`)
- `scripts/status.py` shows how much has been collected
- `deploy/` systemd unit for running the collector on a VM
- `docs/gcp-setup.md` how to get it running on Google Cloud

## Running it locally

```
pip install -r requirements.txt
export NTA_API_KEY=your-key
python -m collector.run
```

Get a key by registering at https://developer.nationaltransport.ie and subscribing to the GTFS-R API.

To change the stops or routes, rerun the stop script, for example `python scripts/find_stops.py --main 5029 --routes 41C --count 6`.

## Data collected

| table | what |
| --- | --- |
| `trip_updates` | predicted arrival time and delay for each target stop, every poll |
| `vehicle_positions` | lat/lon of every bus on the route, every poll |
| `weather` | temperature, rain, wind at the main stop |
| `polls` | log of each request, so gaps in the data can be explained later |

Actual arrival times are not stored directly. They get worked out afterwards from this data, either from the bus position being within about 20m of the stop or from the last poll where the stop still showed up in the feed.

## Tests

```
python -m pytest tests
```

import time
from collections import Counter

import requests
from google.transit import gtfs_realtime_pb2 as pb

TU_REL = pb.TripUpdate.StopTimeUpdate.ScheduleRelationship
VP_STATUS = pb.VehiclePosition.VehicleStopStatus


RETRY_STATUS = {429, 500, 502, 503, 504}


def fetch_feed(url, api_key, timeout=20, retries=2, wait=5):
    """Fetch and parse a feed. The API sometimes answers 429 (too many
    requests) even at one request a minute, so try again a couple of times."""
    for attempt in range(retries + 1):
        r = requests.get(url, headers={"x-api-key": api_key}, timeout=timeout)
        if r.status_code in RETRY_STATUS and attempt < retries:
            time.sleep(float(r.headers.get("Retry-After", wait * (attempt + 1))))
            continue
        r.raise_for_status()
        break
    msg = pb.FeedMessage()
    msg.ParseFromString(r.content)
    return msg


def route_key(route_id):
    """The route id was "1 41C c a" in one timetable release and "1_41C_c_a"
    in the next, so compare them without caring about that."""
    return (route_id or "").replace("_", " ").strip().upper()


def _opt(msg, field):
    # protobuf gives 0 for unset numbers, we want to keep None for "not sent"
    return getattr(msg, field) if msg.HasField(field) else None


def route_ids_at_stops(msg, stops):
    """How often each route id appears at our stops, to diagnose a filter that stopped matching."""
    seen = Counter()
    for ent in msg.entity:
        if ent.HasField("trip_update"):
            for stu in ent.trip_update.stop_time_update:
                if stu.stop_id in stops:
                    seen[ent.trip_update.trip.route_id] += 1
    return seen


def trip_update_rows(msg, route_ids, stops, polled_at):
    """One row per stop time update that is for one of our target stops."""
    wanted = {route_key(r) for r in route_ids}
    rows = []
    for ent in msg.entity:
        if not ent.HasField("trip_update"):
            continue
        tu = ent.trip_update
        trip = tu.trip
        # the route id is sometimes missing, so only drop it when it is clearly another route
        if trip.route_id and route_key(trip.route_id) not in wanted:
            continue
        for stu in tu.stop_time_update:
            if stu.stop_id not in stops:
                continue
            rows.append({
                "polled_at": polled_at,
                "trip_id": trip.trip_id,
                "route_id": trip.route_id or None,
                "direction_id": _opt(trip, "direction_id"),
                "start_date": trip.start_date or None,
                "start_time": trip.start_time or None,
                "vehicle_id": tu.vehicle.id or None,
                "stop_id": stu.stop_id,
                "stop_sequence": _opt(stu, "stop_sequence"),
                "arrival_time": stu.arrival.time if stu.HasField("arrival") and stu.arrival.time else None,
                "arrival_delay": _opt(stu.arrival, "delay") if stu.HasField("arrival") else None,
                "departure_time": stu.departure.time if stu.HasField("departure") and stu.departure.time else None,
                "departure_delay": _opt(stu.departure, "delay") if stu.HasField("departure") else None,
                "schedule_relationship": TU_REL.Name(stu.schedule_relationship),
            })
    return rows


def vehicle_rows(msg, route_ids, polled_at):
    """Every live position for the routes we care about, not just near our stops."""
    wanted = {route_key(r) for r in route_ids}
    rows = []
    for ent in msg.entity:
        if not ent.HasField("vehicle"):
            continue
        v = ent.vehicle
        if route_key(v.trip.route_id) not in wanted:
            continue
        rows.append({
            "polled_at": polled_at,
            "vehicle_id": v.vehicle.id or None,
            "trip_id": v.trip.trip_id or None,
            "route_id": v.trip.route_id,
            "direction_id": _opt(v.trip, "direction_id"),
            "start_date": v.trip.start_date or None,
            "start_time": v.trip.start_time or None,
            "lat": v.position.latitude,
            "lon": v.position.longitude,
            "bearing": _opt(v.position, "bearing"),
            "speed": _opt(v.position, "speed"),
            "position_time": v.timestamp or None,
            "current_stop_sequence": _opt(v, "current_stop_sequence"),
            "stop_id": v.stop_id or None,
            "current_status": VP_STATUS.Name(v.current_status) if v.HasField("current_status") else None,
        })
    return rows

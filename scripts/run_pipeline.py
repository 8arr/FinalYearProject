"""Runs every check in order and stops at the first real failure.

    python scripts/run_pipeline.py              # real data in data/bus.db
    python scripts/run_pipeline.py --sim        # simulated data, works anywhere

Each stage ends as PASS, FAIL, SKIP (not enough data yet) or TFI FAULT
(the live feed looks broken, which is TFI's problem and not a failure here).
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from collector import config, db, feeds  # noqa: E402
from bus import evaluate, fallback, health, review, simulate  # noqa: E402
from bus.arrivals import build_arrivals  # noqa: E402

MIN_ARRIVALS = 20
MAX_FALLBACK_MAE_MIN = 10
MIN_REVIEWS_FOR_GATE = 10
MIN_AGREEMENT = 0.8
HORIZONS = (30, 60)

PASS, FAIL, SKIP, TFI_FAULT = "PASS", "FAIL", "SKIP", "TFI FAULT"


class Context:
    def __init__(self, conn, stops, route_ids, args):
        self.conn = conn
        self.stops = stops
        self.route_ids = route_ids
        self.args = args
        self.arrivals = None
        self.results = {}


def stage_unit_tests(ctx):
    if ctx.args.skip_tests:
        return SKIP, "skipped on request"
    proc = subprocess.run([sys.executable, "-m", "pytest", "-q", "tests"], cwd=ROOT,
                          capture_output=True, text=True)
    last = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else proc.stderr.strip()
    return (PASS if proc.returncode == 0 else FAIL), last


def stage_stored_data(ctx):
    issues, stats = health.check_database(ctx.conn, now=ctx.args.now)
    detail = "; ".join(f"{i.level}: {i.text}" for i in issues) or "no problems"
    detail += f" (largest gap {stats.get('largest_gap_min', 0):.0f} min)"
    return (FAIL if health.has_errors(issues) else PASS), detail


def stage_live_feed(ctx):
    key = os.environ.get("NTA_API_KEY")
    if ctx.args.skip_live or not key:
        return SKIP, "no API key set or skipped on request"
    problems = []
    for name, url, kind in (("trip updates", config.TRIP_UPDATES_URL, "trip_updates"),
                            ("vehicles", config.VEHICLES_URL, "vehicles")):
        try:
            msg = feeds.fetch_feed(url, key)
        except Exception as e:
            problems.append(f"{name}: could not fetch ({e})")
            continue
        issues = health.check_feed(msg, route_ids=ctx.route_ids, kind=kind)
        problems += [f"{name}: {i.text}" for i in issues if i.level == "error"]
    if problems:
        return TFI_FAULT, "; ".join(problems) + ". Rerun later, the fallback would be used now."
    return PASS, "both feeds fetched and look sane"


def stage_arrivals(ctx):
    ctx.arrivals = build_arrivals(ctx.conn, ctx.stops)
    gps = [a for a in ctx.arrivals if a.gps_time is not None]
    if len(gps) < MIN_ARRIVALS:
        return SKIP, (f"only {len(gps)} of {len(ctx.arrivals)} trips at the stops have a GPS arrival, "
                      f"need {MIN_ARRIVALS}")
    both = sorted(a.feed_time - a.gps_time for a in gps if a.feed_time is not None)
    detail = (f"{len(gps)} of {len(ctx.arrivals)} trips at the stops have a GPS arrival "
              f"({len(gps) / len(ctx.arrivals):.0%})")
    if both:
        detail += (f"; the feed method (cross check only) is a median {both[len(both) // 2]:.0f}s "
                   f"later over {len(both)} trips")
    return PASS, detail


def stage_accuracy(ctx):
    outcomes, lines = [], []
    for h in HORIZONS:
        r = evaluate.run(ctx.conn, ctx.stops, h, interval=60)
        ctx.results[h] = r
        if not r["enough_data"]:
            outcomes.append(SKIP)
            lines.append(f"{h} min: not enough data (train {r['train']}, test {r['test']})")
            continue
        lo, hi = r["gain_seconds_ci95"]
        lines.append(f"{h} min: model MAE {r['model']['mae_min']:.2f} vs TFI {r['tfi']['mae_min']:.2f} "
                     f"min, {r['verdict']} ({lo:.0f}s to {hi:.0f}s)")
        outcomes.append(FAIL if r["verdict"] == "worse" else PASS)
    if ctx.args.json:
        with open(ctx.args.json, "w") as f:
            json.dump(ctx.results, f, indent=2)
    status = FAIL if FAIL in outcomes else (SKIP if all(o == SKIP for o in outcomes) else PASS)
    return status, "\n      ".join(lines)


def stage_fallback(ctx):
    errors = []
    for stop_id in ctx.stops:
        errors += fallback.backtest(ctx.arrivals, stop_id)
    if len(errors) < MIN_ARRIVALS:
        return SKIP, f"only {len(errors)} slots could be backtested, need more days of data"
    mae = sum(abs(e) for e in errors) / len(errors) / 60
    detail = f"fallback on the latest day: {len(errors)} buses, average error {mae:.1f} min"
    return (PASS if mae <= MAX_FALLBACK_MAE_MIN else FAIL), detail


def stage_human_review(ctx):
    review.ensure_table(ctx.conn)
    s = review.review_summary(ctx.conn)
    if s["reviewed"] == 0:
        return SKIP, "nothing reviewed yet, run python -m bus.review"
    detail = f"{s['reviewed']} cases reviewed, you agreed with {s['agreement']:.0%}"
    if s["reviewed"] >= MIN_REVIEWS_FOR_GATE and s["agreement"] < MIN_AGREEMENT:
        return FAIL, detail + f" (below {MIN_AGREEMENT:.0%})"
    return PASS, detail


STAGES = [
    ("unit tests", stage_unit_tests),
    ("stored data quality", stage_stored_data),
    ("live feed check", stage_live_feed),
    ("arrival detection", stage_arrivals),
    ("accuracy against TFI", stage_accuracy),
    ("fallback without TFI", stage_fallback),
    ("human review", stage_human_review),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=config.DB_PATH)
    ap.add_argument("--sim", action="store_true", help="use freshly simulated data")
    ap.add_argument("--skip-tests", action="store_true")
    ap.add_argument("--skip-live", action="store_true")
    ap.add_argument("--json", help="write the accuracy results here")
    args = ap.parse_args()
    args.now = time.time()

    if args.sim:
        path = os.path.join(tempfile.mkdtemp(), "sim.db")
        conn = db.connect(path)
        simulate.simulate(conn, days=14, delay_only=True)
        stops = {simulate.STOP["stop_id"]: simulate.STOP}
        route_ids = {simulate.ROUTE_ID}
        args.now = max(r[0] for r in conn.execute("SELECT polled_at FROM polls")) + 60
        args.skip_live = True
    else:
        route_ids, stops = config.load_targets()
        conn = db.connect(args.db)

    ctx = Context(conn, stops, route_ids, args)
    worst = PASS
    for name, stage in STAGES:
        status, detail = stage(ctx)
        print(f"[{status:^9}] {name}\n      {detail}")
        if status == FAIL:
            worst = FAIL
            break
        if status == TFI_FAULT and worst == PASS:
            worst = TFI_FAULT

    print()
    if worst == FAIL:
        print("RESULT: FAIL, fix the stage above before deploying")
        sys.exit(1)
    if worst == TFI_FAULT:
        print("RESULT: OK, but the live feed check found a TFI side problem, rerun to be sure")
    else:
        print("RESULT: PASS")


if __name__ == "__main__":
    main()

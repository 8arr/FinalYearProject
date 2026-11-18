"""Small local web page for checking results by eye.

It shows one bus at a time: where the bus was, when we decided it arrived,
and what TFI and the model each predicted. You answer one question, "does
the detected arrival time look right?", and the answers are saved in the
database so the test pipeline can report how often you agreed.

    python -m bus.review --horizon 30
    then open http://127.0.0.1:8000
"""
import argparse
import html
import random
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs

from .arrivals import RADIUS_M, build_arrivals
from .dataset import TZ, build_samples
from .evaluate import split_by_day
from .geo import distance_m
from .model import CorrectionModel

SCHEMA = """
CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY,
    trip_id TEXT NOT NULL,
    start_date TEXT,
    stop_id TEXT NOT NULL,
    horizon_min INTEGER NOT NULL,
    arrival_ok INTEGER NOT NULL,
    note TEXT,
    reviewed_at INTEGER NOT NULL
);
"""


def ensure_table(conn):
    conn.executescript(SCHEMA)


def record_review(conn, case_key, horizon, arrival_ok, note="", now=None):
    trip_id, start_date, stop_id = case_key
    conn.execute(
        "INSERT INTO reviews (trip_id, start_date, stop_id, horizon_min, arrival_ok, note, reviewed_at)"
        " VALUES (?,?,?,?,?,?,?)",
        (trip_id, start_date, stop_id, horizon, int(arrival_ok), note, int(now or time.time())))
    conn.commit()


def review_summary(conn):
    ensure_table(conn)
    total, ok = conn.execute("SELECT COUNT(*), COALESCE(SUM(arrival_ok), 0) FROM reviews").fetchone()
    return {"reviewed": total, "agreed": int(ok), "agreement": (ok / total) if total else None}


def _reviewed_keys(conn, horizon):
    return {tuple(r) for r in conn.execute(
        "SELECT trip_id, start_date, stop_id FROM reviews WHERE horizon_min = ?", (horizon,))}


def build_cases(conn, stops, horizon, truth="best", limit=40, seed=0):
    """Test-set arrivals with TFI and model predictions, in random order."""
    ensure_table(conn)
    arrivals = build_arrivals(conn, stops)
    by_key = {(a.trip_id, a.start_date, a.stop_id): a for a in arrivals}
    samples = build_samples(conn, arrivals, list(stops), horizon, truth)
    train, test = split_by_day(samples)

    model = CorrectionModel().fit(train) if len(train) >= 30 else None
    pool = test or samples
    preds = model.predict(pool) if model else [None] * len(pool)

    cases = []
    for s, p in zip(pool, preds):
        key = (s["trip_id"], s["start_date"], s["stop_id"])
        cases.append({"key": key, "arrival": by_key[key], "actual": s["actual"],
                      "tfi": s["tfi_time"], "model": p, "stop": stops[s["stop_id"]]})
    random.Random(seed).shuffle(cases)
    done = _reviewed_keys(conn, horizon)
    return [c for c in cases if c["key"] not in done][:limit]


def distance_series(conn, case):
    stop = case["stop"]
    rows = conn.execute(
        "SELECT COALESCE(position_time, polled_at), lat, lon FROM vehicle_positions"
        " WHERE trip_id = ? AND start_date IS ? ORDER BY 1", case["key"][:2]).fetchall()
    return [(t, distance_m(stop["lat"], stop["lon"], la, lo)) for t, la, lo in rows]


def clock(epoch):
    return datetime.fromtimestamp(epoch, TZ).strftime("%H:%M:%S")


def describe_error(predicted, actual):
    diff = round(predicted - actual)
    if abs(diff) < 5:
        return "spot on"
    m, s = divmod(abs(diff), 60)
    amount = f"{m} min {s} s" if m else f"{s} s"
    return f"{amount} {'late' if diff > 0 else 'early'}"


def chart_svg(series, case, width=640, height=220, window=(-40, 10)):
    actual = case["actual"]
    pts = [((t - actual) / 60, d) for t, d in series if window[0] <= (t - actual) / 60 <= window[1]]
    if not pts:
        return "<p><i>No GPS track for this bus, the arrival time came from the feed.</i></p>"
    max_d = max(max(d for _, d in pts), 100)
    left, bottom, top = 50, height - 30, 10

    def x(minutes):
        return left + (minutes - window[0]) / (window[1] - window[0]) * (width - left - 10)

    def y(d):
        return bottom - d / max_d * (bottom - top)

    line = " ".join(f"{x(m):.1f},{y(d):.1f}" for m, d in pts)
    marks = [("detected arrival", 0, "#2a9d4b")]
    marks.append(("TFI", (case["tfi"] - actual) / 60, "#d1495b"))
    if case["model"] is not None:
        marks.append(("model", (case["model"] - actual) / 60, "#2f6fdb"))

    out = [f'<svg width="{width}" height="{height}" style="background:#fafafa;border:1px solid #ddd">',
           f'<line x1="{left}" y1="{y(RADIUS_M):.1f}" x2="{width - 10}" y2="{y(RADIUS_M):.1f}" '
           f'stroke="#aaa" stroke-dasharray="3,3"/>',
           f'<text x="{left + 4}" y="{y(RADIUS_M) - 3:.1f}" font-size="10" fill="#777">{RADIUS_M} m</text>',
           f'<polyline points="{line}" fill="none" stroke="#444" stroke-width="2"/>']
    for i, (label, minutes, colour) in enumerate(marks):
        if window[0] <= minutes <= window[1]:
            out.append(f'<line x1="{x(minutes):.1f}" y1="{top}" x2="{x(minutes):.1f}" y2="{bottom}" '
                       f'stroke="{colour}" stroke-width="2"/>')
        out.append(f'<text x="{left + 90}" y="{top + 14 + i * 14}" font-size="12" fill="{colour}">'
                   f'&#9632; {label}</text>')
    out.append(f'<text x="{left}" y="{height - 8}" font-size="11" fill="#555">'
               f"minutes before and after the detected arrival</text>")
    out.append(f'<text x="4" y="{top + 10}" font-size="11" fill="#555">{max_d:.0f} m</text>')
    out.append("</svg>")
    return "".join(out)


def render_case(conn, case, position, total, horizon):
    series = distance_series(conn, case)
    a = case["arrival"]
    actual = case["actual"]
    rows = [("Detected arrival", clock(actual), "")]
    rows.append(("TFI said", clock(case["tfi"]), describe_error(case["tfi"], actual)))
    if case["model"] is not None:
        rows.append(("Model said", clock(case["model"]), describe_error(case["model"], actual)))
    gps = clock(a.gps_time) if a.gps_time is not None else "none"
    feed = clock(a.feed_time) if a.feed_time is not None else "none"
    table = "".join(f"<tr><td>{html.escape(n)}</td><td><b>{html.escape(t)}</b></td><td>{html.escape(e)}</td></tr>"
                    for n, t, e in rows)
    summary = review_summary(conn)
    done = f"{summary['reviewed']} reviewed so far"
    if summary["reviewed"]:
        done += f", you agreed with the detected time {summary['agreement']:.0%} of the time"
    date = datetime.fromtimestamp(actual, TZ).strftime("%A %d %B %Y")

    return f"""<!doctype html><html><head><meta charset="utf-8"><title>Check results</title>
<style>body{{font-family:sans-serif;max-width:700px;margin:2em auto;color:#222}}
td{{padding:3px 14px 3px 0}} button{{font-size:1.1em;padding:.6em 1.2em;margin-right:.5em;cursor:pointer}}
.ok{{background:#d7f0dd}} .bad{{background:#f6d6da}} small{{color:#666}}</style></head><body>
<h2>Case {position} of {total}</h2>
<p>{html.escape(case['stop']['name'])} ({html.escape(case['stop']['stop_code'])}), {date}, trip
<code>{html.escape(case['key'][0])}</code>, {horizon} minute prediction<br><small>{done}</small></p>
{chart_svg(series, case)}
<table>{table}</table>
<p><small>GPS method: {gps}. Feed method: {feed}.</small></p>
<form method="post" action="/review">
<p><b>Does the detected arrival time look right?</b> The grey line is the distance of the bus from
the stop, it should reach the dashed line at the green marker.</p>
<p><input name="note" placeholder="optional note" size="50"></p>
<button class="ok" name="answer" value="yes">Looks right</button>
<button class="bad" name="answer" value="no">Looks wrong</button>
<button name="answer" value="skip">Skip</button>
</form></body></html>"""


def render_done(conn):
    s = review_summary(conn)
    pct = f"{s['agreement']:.0%}" if s["agreement"] is not None else "n/a"
    return (f"<!doctype html><meta charset='utf-8'><body style='font-family:sans-serif;margin:2em'>"
            f"<h2>All done</h2><p>{s['reviewed']} cases reviewed, agreement {pct}.</p></body>")


def make_handler(conn, cases, horizon):
    queue = list(cases)
    total = len(queue)

    class Handler(BaseHTTPRequestHandler):
        def _send(self, body, code=200):
            data = body.encode()
            self.send_response(code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if queue:
                self._send(render_case(conn, queue[0], total - len(queue) + 1, total, horizon))
            else:
                self._send(render_done(conn))

        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            form = parse_qs(self.rfile.read(length).decode())
            answer = form.get("answer", ["skip"])[0]
            if queue and answer in ("yes", "no"):
                record_review(conn, queue[0]["key"], horizon, answer == "yes",
                              form.get("note", [""])[0])
            if queue:
                queue.pop(0)
            self.send_response(303)
            self.send_header("Location", "/")
            self.end_headers()

        def log_message(self, *args):
            pass

    return Handler


def main():
    from collector import config, db

    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=config.DB_PATH)
    ap.add_argument("--horizon", type=int, default=30)
    ap.add_argument("--truth", default="best", choices=["gps", "feed", "best"])
    ap.add_argument("--cases", type=int, default=40)
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()

    _, stops = config.load_targets()
    conn = db.connect(args.db)
    ensure_table(conn)
    cases = build_cases(conn, stops, args.horizon, args.truth, args.cases)
    print(f"{len(cases)} cases to check, open http://127.0.0.1:{args.port} (Ctrl+C to stop)")
    HTTPServer(("127.0.0.1", args.port), make_handler(conn, cases, args.horizon)).serve_forever()


if __name__ == "__main__":
    main()

"""Draws the project plan chart. Edit the tasks and dates below, then run

    pip install matplotlib
    python report/make_gantt.py
"""
import os
from datetime import date

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt

TODAY = date(2026, 11, 18)

# (name, start, end, status)  status: done, ongoing, planned, buffer
TASKS = [
    ("Topic choice and supervisor meetings", date(2026, 10, 12), date(2026, 11, 9), "done"),
    ("Stop selection, API key, cloud server setup", date(2026, 11, 9), date(2026, 11, 12), "done"),
    ("Collector running, nightly backups", date(2026, 11, 10), date(2026, 11, 13), "done"),
    ("Arrival detection, model, fallback, tests, review page", date(2026, 11, 12), date(2026, 11, 19), "done"),
    ("Draft proposal and interim report", date(2026, 11, 17), date(2026, 11, 19), "done"),
    ("Look at first real data, find and fix collector fault", date(2026, 11, 18), date(2026, 11, 19), "done"),
    ("First data stored correctly (11 Nov evening only)", date(2026, 11, 11), date(2026, 11, 12), "done"),
    ("Redeploy fixed collector, load timetable", date(2026, 11, 18), date(2026, 11, 23), "planned"),
    ("Data collection (continuous, restarted)", date(2026, 11, 22), date(2027, 3, 5), "ongoing"),
    ("Run pipeline on new data, fix problems", date(2026, 12, 1), date(2026, 12, 12), "planned"),
    ("Rewrite and send proposal", date(2026, 11, 19), date(2026, 11, 26), "planned"),
    ("Check 50+ cases by hand", date(2026, 12, 7), date(2026, 12, 14), "planned"),
    ("Finish interim report", date(2026, 11, 23), date(2026, 12, 14), "planned"),
    ("Interim demo preparation", date(2026, 12, 10), date(2026, 12, 17), "planned"),
    ("Ratings: form design and ethics check", date(2026, 12, 7), date(2027, 1, 9), "planned"),
    ("Traffic input (bus speeds first)", date(2026, 12, 14), date(2027, 1, 9), "planned"),
    ("Holidays, reduced work", date(2026, 12, 21), date(2027, 1, 4), "buffer"),
    ("Model improvements and comparisons", date(2027, 1, 11), date(2027, 2, 6), "planned"),
    ("Ratings collection", date(2027, 1, 11), date(2027, 2, 13), "planned"),
    ("Deployment of the estimate service", date(2027, 2, 8), date(2027, 2, 27), "planned"),
    ("Ratings analysis", date(2027, 2, 15), date(2027, 2, 27), "planned"),
    ("Final evaluation on all data", date(2027, 2, 22), date(2027, 3, 6), "planned"),
    ("Final report writing", date(2027, 1, 11), date(2027, 3, 13), "planned"),
    ("Code clean up and documentation", date(2027, 3, 1), date(2027, 3, 13), "planned"),
    ("Buffer", date(2027, 3, 15), date(2027, 3, 27), "buffer"),
]

COLOURS = {"done": "#2a9d4b", "ongoing": "#8ecae6", "planned": "#2f6fdb", "buffer": "#bbbbbb"}


def main():
    fig, ax = plt.subplots(figsize=(13, 8))
    for i, (name, start, end, status) in enumerate(TASKS):
        ax.barh(i, (end - start).days, left=mdates.date2num(start), color=COLOURS[status], height=0.6)
    ax.set_yticks(range(len(TASKS)))
    ax.set_yticklabels([t[0] for t in TASKS], fontsize=9)
    ax.invert_yaxis()
    ax.xaxis_date()
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_minor_locator(mdates.WeekdayLocator(byweekday=mdates.MO))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.grid(axis="x", which="major", color="#999999")
    ax.grid(axis="x", which="minor", color="#e5e5e5")
    ax.axvline(mdates.date2num(TODAY), color="#d1495b", linewidth=2)
    ax.text(mdates.date2num(TODAY), -0.9, " today", color="#d1495b", fontsize=9)
    ax.legend(handles=[plt.Rectangle((0, 0), 1, 1, color=c) for c in COLOURS.values()],
              labels=["done", "ongoing", "planned", "holiday or buffer"], loc="lower left", fontsize=9)
    ax.set_title("Project plan (draft)")
    fig.tight_layout()
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gantt.png")
    fig.savefig(out, dpi=130)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()

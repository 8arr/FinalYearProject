import os
import subprocess
import sys

from collector import db
from bus import simulate

ROOT = os.path.join(os.path.dirname(__file__), "..")


def test_overview_script_runs_on_a_database(tmp_path):
    path = str(tmp_path / "bus.db")
    conn = db.connect(path)
    simulate.simulate(conn, days=2)
    conn.close()

    out = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "data_overview.py"), path],
                         capture_output=True, text=True, check=True).stdout
    assert "collected from" in out
    assert "arrival_time" in out
    assert "per stop" in out

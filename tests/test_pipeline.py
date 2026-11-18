import importlib.util
import os
import sqlite3
from types import SimpleNamespace

import pytest

from bus import review
from collector import config, db
from tests.conftest import STOPS

path = os.path.join(os.path.dirname(__file__), "..", "scripts", "run_pipeline.py")
spec = importlib.util.spec_from_file_location("run_pipeline", path)
pipeline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pipeline)


def context(conn, **args):
    defaults = dict(skip_live=False, skip_tests=True, json=None, now=1_800_000_000)
    defaults.update(args)
    return pipeline.Context(conn, STOPS, {"1 41C c a"}, SimpleNamespace(**defaults))


def test_empty_database_fails_the_pipeline():
    status, _ = pipeline.stage_stored_data(context(db.connect(":memory:")))
    assert status == pipeline.FAIL


def test_tfi_being_down_is_not_a_failure(monkeypatch):
    monkeypatch.setenv("NTA_API_KEY", "key")
    monkeypatch.setattr(config, "TRIP_UPDATES_URL", "http://127.0.0.1:9/TripUpdates")
    monkeypatch.setattr(config, "VEHICLES_URL", "http://127.0.0.1:9/Vehicles")
    status, detail = pipeline.stage_live_feed(context(db.connect(":memory:")))
    assert status == pipeline.TFI_FAULT
    assert "fallback" in detail


def test_live_check_is_skipped_without_a_key(monkeypatch):
    monkeypatch.delenv("NTA_API_KEY", raising=False)
    assert pipeline.stage_live_feed(context(db.connect(":memory:")))[0] == pipeline.SKIP


def test_human_review_gate():
    conn = sqlite3.connect(":memory:")
    review.ensure_table(conn)
    ctx = context(conn)
    assert pipeline.stage_human_review(ctx)[0] == pipeline.SKIP
    for i in range(12):
        review.record_review(conn, (f"t{i}", "d", "s"), 30, i < 11)
    assert pipeline.stage_human_review(ctx)[0] == pipeline.PASS
    for i in range(12, 40):
        review.record_review(conn, (f"t{i}", "d", "s"), 30, False)
    assert pipeline.stage_human_review(ctx)[0] == pipeline.FAIL


def test_accuracy_stage_fails_when_the_model_is_worse(sim, monkeypatch):
    conn, _ = sim
    worse = {"enough_data": True, "verdict": "worse", "gain_seconds_ci95": [-30, -10],
             "model": {"mae_min": 2.0}, "tfi": {"mae_min": 1.0}}
    monkeypatch.setattr(pipeline.evaluate, "run", lambda *a, **k: dict(worse))
    assert pipeline.stage_accuracy(context(conn))[0] == pipeline.FAIL

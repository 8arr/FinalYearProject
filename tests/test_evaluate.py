import numpy as np
import pytest

from bus import evaluate
from bus.arrivals import build_arrivals
from bus.dataset import build_samples
from bus.model import CorrectionModel


def samples_for(conn, stops, horizon):
    arrivals = build_arrivals(conn, stops)
    return arrivals, build_samples(conn, arrivals, list(stops), horizon)


def test_metrics_on_known_errors():
    m = evaluate.metrics([60, -60, 120, 0])
    assert m["n"] == 4
    assert m["mae_min"] == pytest.approx(1.0)
    assert m["bias_min"] == pytest.approx(0.5)
    assert m["within_1min"] == pytest.approx(0.75)
    assert m["within_2min"] == 1.0


def test_bootstrap_interval_and_verdict():
    a = np.full(100, 120.0)
    assert evaluate.verdict(*evaluate.paired_bootstrap(a, a - 30)) == "better"
    assert evaluate.verdict(*evaluate.paired_bootstrap(a, a + 30)) == "worse"
    rng = np.random.default_rng(0)
    noise = rng.normal(0, 20, 100)
    assert evaluate.verdict(*evaluate.paired_bootstrap(a, a + noise)) == "inconclusive"


def test_samples_are_picked_from_what_tfi_said_not_from_the_real_arrival(sim, stops):
    conn, _ = sim
    arrivals, samples = samples_for(conn, stops, 30)
    assert len(samples) == len(arrivals)
    # if the poll had been chosen using the real arrival time, this would vary a lot
    assert all(abs(s["tfi_eta_min"] - 30) <= 2 for s in samples)


def test_split_puts_test_days_after_train_days(sim, stops):
    conn, _ = sim
    _, samples = samples_for(conn, stops, 30)
    train, test = evaluate.split_by_day(samples)
    assert train and test
    assert max(s["actual"] for s in train) < min(s["actual"] for s in test)


@pytest.mark.parametrize("horizon", [30, 60])
def test_model_beats_tfi_when_there_is_something_to_learn(sim, stops, horizon):
    conn, _ = sim
    result = evaluate.run(conn, stops, horizon)
    assert result["verdict"] == "better"
    assert result["model"]["mae_min"] < result["tfi"]["mae_min"]
    assert result["model"]["mae_min"] < result["median_bias"]["mae_min"]


def test_model_is_not_credited_when_there_is_nothing_to_learn(sim_noise, stops):
    conn, _ = sim_noise
    result = evaluate.run(conn, stops, 30)
    assert result["verdict"] != "better"


def test_time_of_day_is_kept_as_a_useful_input(sim, stops):
    conn, _ = sim
    _, samples = samples_for(conn, stops, 60)
    check = evaluate.feature_check(samples)
    assert check["time of day"]["keep"] is True
    assert "weather" in check


def test_too_little_data_is_reported_not_guessed(sim, stops):
    conn, _ = sim
    _, samples = samples_for(conn, stops, 30)
    result = evaluate.compare(samples[:20])
    assert result["enough_data"] is False


def test_model_predictions_are_epoch_times_near_tfi(sim, stops):
    conn, _ = sim
    _, samples = samples_for(conn, stops, 30)
    pred = CorrectionModel().fit(samples).predict(samples[:5])
    for p, s in zip(pred, samples[:5]):
        assert abs(p - s["tfi_time"]) < 15 * 60

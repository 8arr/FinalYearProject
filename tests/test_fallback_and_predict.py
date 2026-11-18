from datetime import datetime

import pytest

from bus import fallback, predict
from bus.arrivals import build_arrivals
from bus.dataset import TZ
from tests.conftest import STOP_ID, STOPS
from tests.test_health import NOW, trip_feed


def local(year, month, day, hour, minute):
    return datetime(year, month, day, hour, minute, tzinfo=TZ).timestamp()


@pytest.fixture(scope="module")
def noise_arrivals(sim_noise):
    conn, _ = sim_noise
    return build_arrivals(conn, STOPS)


def test_history_estimate_finds_the_next_timetable_slots(noise_arrivals):
    # 2 Nov 2026 is a Monday, in the noise data buses are at the stop at :00, :20 and :40
    now = local(2026, 11, 16, 8, 5)
    est = fallback.estimate_from_history(noise_arrivals, STOP_ID, now, n=3)
    expected = [local(2026, 11, 16, 8, 20), local(2026, 11, 16, 8, 40), local(2026, 11, 16, 9, 0)]
    assert len(est) == 3
    for e, want in zip(est, expected):
        assert e.time == pytest.approx(want, abs=90)
        assert e.observations >= 3


def test_history_estimate_does_not_mix_weekdays_into_weekends(noise_arrivals):
    # only two Saturdays and two Sundays of data, too few to trust
    saturday = local(2026, 11, 21, 8, 5)
    assert fallback.estimate_from_history(noise_arrivals, STOP_ID, saturday) == []


def test_history_estimate_rolls_over_to_tomorrow_late_at_night(noise_arrivals):
    now = local(2026, 11, 16, 23, 50)
    est = fallback.estimate_from_history(noise_arrivals, STOP_ID, now, n=1)
    assert est[0].time == pytest.approx(local(2026, 11, 17, 6, 0), abs=90)


def test_backtest_errors_are_small_on_regular_data(noise_arrivals):
    errors = fallback.backtest(noise_arrivals, STOP_ID)
    assert len(errors) > 30
    assert sum(abs(e) for e in errors) / len(errors) < 90


def no_history(now, n):
    return [fallback.HistoryEstimate(now + 600, "slot", 5, 2.0)]


def test_live_feed_is_used_when_healthy():
    msg = trip_feed(arrival_offset=600)
    result = predict.estimate_next("s", lambda: msg, no_history, now=NOW)
    assert result.source == "tfi"
    assert result.estimates[0].time == NOW + 600


def test_fallback_is_used_when_tfi_is_unreachable():
    def down():
        raise ConnectionError("no route to host")
    result = predict.estimate_next("s", down, no_history, now=NOW)
    assert result.source == "history"
    assert result.estimates[0].time == NOW + 600
    assert any("could not reach" in n for n in result.notes)


def test_fallback_is_used_when_the_feed_is_stale():
    msg = trip_feed(timestamp=NOW - 7200)
    result = predict.estimate_next("s", lambda: msg, no_history, now=NOW)
    assert result.source == "history"
    assert any("stale" in n for n in result.notes)


def test_fallback_is_used_when_the_feed_is_nonsense():
    msg = trip_feed(delays=[99999, 99999, 99999])
    assert predict.estimate_next("s", lambda: msg, no_history, now=NOW).source == "history"


class PlusTwoMinutes:
    def predict(self, samples):
        return [s["tfi_time"] + 120 for s in samples]


def test_model_only_adjusts_buses_in_its_range():
    near = predict.estimate_next("s", lambda: trip_feed(arrival_offset=300), no_history,
                                 now=NOW, model=PlusTwoMinutes())
    far = predict.estimate_next("s", lambda: trip_feed(arrival_offset=1800), no_history,
                                now=NOW, model=PlusTwoMinutes())
    assert near.estimates[0].time == NOW + 300
    assert far.estimates[0].time == NOW + 1800 + 120
    assert far.estimates[0].tfi_time == NOW + 1800

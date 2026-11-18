import pytest

from bus.geo import closest_on_segment, distance_m

STOP = (53.445076, -6.234542)


def north_of(lat, metres):
    return lat + metres / 111_320


def test_distance_known_value():
    assert distance_m(53.0, -6.0, north_of(53.0, 100), -6.0) == pytest.approx(100, abs=0.5)


def test_segment_passing_the_stop():
    a = (north_of(STOP[0], -200), STOP[1])
    b = (north_of(STOP[0], 200), STOP[1])
    dist, frac = closest_on_segment(a, b, STOP)
    assert dist == pytest.approx(0, abs=0.5)
    assert frac == pytest.approx(0.5, abs=0.01)


def test_segment_that_stops_short_clamps_to_the_end():
    a = (north_of(STOP[0], -300), STOP[1])
    b = (north_of(STOP[0], -100), STOP[1])
    dist, frac = closest_on_segment(a, b, STOP)
    assert dist == pytest.approx(100, abs=0.5)
    assert frac == 1.0


def test_zero_length_segment():
    dist, frac = closest_on_segment(STOP, STOP, STOP)
    assert dist == 0 and frac == 0

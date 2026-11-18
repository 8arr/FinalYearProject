from bus import schedule


def test_service_day_start_is_local_midnight():
    # 1 Nov 2026 is winter time (UTC+0), 1 Jul 2026 is summer time (UTC+1)
    assert schedule.service_day_start("20261101") == 1_793_491_200
    assert schedule.service_day_start("20260701") == 1_782_860_400


def test_predicted_time_prefers_the_clock_time_from_the_feed():
    assert schedule.predicted_time(5000, 30, "20261101", 100) == 5000


def test_predicted_time_is_timetable_plus_delay():
    start = schedule.service_day_start("20261101")
    assert schedule.predicted_time(None, 90, "20261101", 3600) == start + 3600 + 90
    assert schedule.predicted_time(0, -30, "20261101", 3600) == start + 3600 - 30


def test_predicted_time_unknown_without_what_it_needs():
    assert schedule.predicted_time(None, None, "20261101", 3600) is None
    assert schedule.predicted_time(None, 30, None, 3600) is None
    assert schedule.predicted_time(None, 30, "20261101", None) is None


def test_trips_after_midnight_use_times_past_24_hours():
    start = schedule.service_day_start("20261101")
    assert schedule.predicted_time(None, 0, "20261101", 25 * 3600) == start + 25 * 3600

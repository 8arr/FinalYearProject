import math

M_PER_DEG = 111_320


def to_xy(lat, lon, lat0, lon0):
    """Metres east and north of a reference point. Fine over a few km."""
    x = (lon - lon0) * M_PER_DEG * math.cos(math.radians(lat0))
    y = (lat - lat0) * M_PER_DEG
    return x, y


def distance_m(lat1, lon1, lat2, lon2):
    x, y = to_xy(lat2, lon2, lat1, lon1)
    return math.hypot(x, y)


def closest_on_segment(p0, p1, stop):
    """Closest approach of a straight segment to the stop.

    Points are (lat, lon). Returns (distance in metres, fraction along the
    segment from 0 to 1).
    """
    lat0, lon0 = stop
    ax, ay = to_xy(p0[0], p0[1], lat0, lon0)
    bx, by = to_xy(p1[0], p1[1], lat0, lon0)
    dx, dy = bx - ax, by - ay
    length_sq = dx * dx + dy * dy
    if length_sq == 0:
        return math.hypot(ax, ay), 0.0
    frac = -(ax * dx + ay * dy) / length_sq
    frac = max(0.0, min(1.0, frac))
    return math.hypot(ax + frac * dx, ay + frac * dy), frac

"""The prediction model.

It does not predict the arrival time from scratch. It learns how far off
TFI usually is in a given situation and corrects for that, so if there is
nothing to learn it falls back to roughly what TFI said.
"""
import argparse
import pickle

import numpy as np
from sklearn.ensemble import GradientBoostingRegressor

FEATURES = ["tfi_eta_min", "tfi_delay_min", "hour", "is_weekend", "rain_mm", "wind_kmh"]
FEATURE_GROUPS = {
    "time of day": ["hour", "is_weekend"],
    "weather": ["rain_mm", "wind_kmh"],
}


def matrix(samples, features):
    return np.array([[s[f] for f in features] for s in samples], dtype=float)


def corrections(samples):
    """How many seconds the real arrival differed from TFI's prediction."""
    return np.array([s["actual"] - s["tfi_time"] for s in samples], dtype=float)


class CorrectionModel:
    def __init__(self, features=FEATURES):
        self.features = list(features)
        self.reg = GradientBoostingRegressor(
            loss="absolute_error", n_estimators=150, max_depth=2,
            learning_rate=0.05, subsample=0.8, random_state=0)

    def fit(self, samples):
        self.reg.fit(matrix(samples, self.features), corrections(samples))
        return self

    def predict(self, samples):
        """Predicted arrival times as epoch seconds."""
        tfi = np.array([s["tfi_time"] for s in samples], dtype=float)
        return tfi + self.reg.predict(matrix(samples, self.features))


class MedianBias:
    """Baseline: shift TFI by its typical error and nothing else."""

    def fit(self, samples):
        self.shift = float(np.median(corrections(samples)))
        return self

    def predict(self, samples):
        return np.array([s["tfi_time"] for s in samples], dtype=float) + self.shift


def save(model, path):
    with open(path, "wb") as f:
        pickle.dump(model, f)


def load(path):
    with open(path, "rb") as f:
        return pickle.load(f)


def main():
    from collector import config, db
    from .arrivals import build_arrivals
    from .dataset import build_samples

    ap = argparse.ArgumentParser(description="train on everything in the database and save the model")
    ap.add_argument("--db", default=config.DB_PATH)
    ap.add_argument("--horizon", type=int, default=30)
    ap.add_argument("--truth", default="gps", choices=["gps", "feed"])
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    _, stops = config.load_targets()
    conn = db.connect(args.db)
    arrivals = build_arrivals(conn, stops)
    samples = build_samples(conn, arrivals, list(stops), args.horizon, args.truth)
    if len(samples) < 50:
        raise SystemExit(f"only {len(samples)} samples, need more data first")
    save(CorrectionModel().fit(samples), args.out)
    print(f"trained on {len(samples)} samples, saved to {args.out}")


if __name__ == "__main__":
    main()

"""Compare the model against plain TFI on arrivals it has not seen.

    python -m bus.evaluate --horizon 30
    python -m bus.evaluate --horizon 60 --truth feed
"""
import argparse
import json
from datetime import datetime

import numpy as np

from .arrivals import build_arrivals
from .dataset import TZ, build_samples
from .model import FEATURE_GROUPS, FEATURES, CorrectionModel, MedianBias


def metrics(errors_s):
    """errors_s: predicted minus actual, in seconds."""
    e = np.asarray(errors_s, dtype=float)
    a = np.abs(e)
    return {
        "n": int(len(e)),
        "mae_min": float(a.mean() / 60),
        "median_ae_min": float(np.median(a) / 60),
        "rmse_min": float(np.sqrt((e ** 2).mean()) / 60),
        "bias_min": float(e.mean() / 60),
        "within_1min": float((a <= 60).mean()),
        "within_2min": float((a <= 120).mean()),
    }


def split_by_day(samples, test_fraction=0.3):
    """Earlier days train, later days test, so nothing from the future leaks in."""
    days = sorted({datetime.fromtimestamp(s["actual"], TZ).date() for s in samples})
    if len(days) < 2:
        return samples, []
    n_test = max(1, round(len(days) * test_fraction))
    test_days = set(days[-n_test:])
    train = [s for s in samples if datetime.fromtimestamp(s["actual"], TZ).date() not in test_days]
    test = [s for s in samples if datetime.fromtimestamp(s["actual"], TZ).date() in test_days]
    return train, test


def paired_bootstrap(abs_a, abs_b, rounds=2000, seed=0):
    """95% interval for the mean of (abs_a - abs_b). Positive means b is better."""
    diff = np.asarray(abs_a) - np.asarray(abs_b)
    rng = np.random.default_rng(seed)
    means = [rng.choice(diff, len(diff)).mean() for _ in range(rounds)]
    lo, hi = np.percentile(means, [2.5, 97.5])
    return float(lo), float(hi)


def verdict(lo, hi):
    if lo > 0:
        return "better"
    if hi < 0:
        return "worse"
    return "inconclusive"


def _actuals(samples):
    return np.array([s["actual"] for s in samples], dtype=float)


def compare(samples, min_samples=30):
    train, test = split_by_day(samples)
    if len(train) < min_samples or len(test) < min_samples:
        return {"enough_data": False, "train": len(train), "test": len(test)}

    actual = _actuals(test)
    tfi = np.array([s["tfi_time"] for s in test], dtype=float)
    bias_pred = MedianBias().fit(train).predict(test)
    model_pred = CorrectionModel().fit(train).predict(test)

    lo, hi = paired_bootstrap(np.abs(tfi - actual), np.abs(model_pred - actual))
    return {
        "enough_data": True,
        "train": len(train),
        "test": len(test),
        "tfi": metrics(tfi - actual),
        "median_bias": metrics(bias_pred - actual),
        "model": metrics(model_pred - actual),
        "gain_seconds_ci95": [lo, hi],
        "verdict": verdict(lo, hi),
    }


def feature_check(samples, min_samples=30):
    """Does the model get better or worse when a group of inputs is removed?

    A group that does not help on unseen days is treated as noise. The same
    idea is how user ratings would be tested once they are collected.
    """
    train, test = split_by_day(samples)
    if len(train) < min_samples or len(test) < min_samples:
        return None
    actual = _actuals(test)

    def test_mae(features):
        pred = CorrectionModel(features).fit(train).predict(test)
        return float(np.abs(pred - actual).mean() / 60)

    full = test_mae(FEATURES)
    out = {"all features": {"mae_min": full, "keep": None}}
    for name, cols in FEATURE_GROUPS.items():
        without = test_mae([f for f in FEATURES if f not in cols])
        out[name] = {"mae_without_min": without, "keep": without > full}
    return out


def run(conn, stops, horizon, truth="gps", interval=60):
    arrivals = build_arrivals(conn, stops, interval=interval)
    samples = build_samples(conn, arrivals, list(stops), horizon, truth)
    result = compare(samples)
    result["horizon_min"] = horizon
    result["truth"] = truth
    result["arrivals_found"] = sum(1 for a in arrivals if a.actual(truth) is not None)
    result["features"] = feature_check(samples)
    return result


def format_result(r):
    lines = [f"horizon {r['horizon_min']} min, truth: {r['truth']}, "
             f"{r['arrivals_found']} arrivals found"]
    if not r["enough_data"]:
        lines.append(f"  not enough data yet (train {r['train']}, test {r['test']})")
        return "\n".join(lines)

    lines.append(f"  train {r['train']}, test {r['test']} (test days are after train days)")
    lines.append(f"  {'':<14}{'MAE':>7}{'median':>8}{'RMSE':>7}{'bias':>7}{'<=1min':>8}{'<=2min':>8}")
    for key, label in (("tfi", "TFI"), ("median_bias", "TFI + bias"), ("model", "model")):
        m = r[key]
        lines.append(
            f"  {label:<14}{m['mae_min']:>7.2f}{m['median_ae_min']:>8.2f}{m['rmse_min']:>7.2f}"
            f"{m['bias_min']:>7.2f}{m['within_1min']:>8.0%}{m['within_2min']:>8.0%}")
    lo, hi = r["gain_seconds_ci95"]
    lines.append(f"  model vs TFI: average saving {lo:.0f}s to {hi:.0f}s per bus (95% interval), "
                 f"verdict: {r['verdict']}")
    if r.get("features"):
        for name, f in r["features"].items():
            if f["keep"] is not None:
                lines.append(f"  inputs '{name}': {'helps' if f['keep'] else 'does not help'} "
                             f"(MAE without {f['mae_without_min']:.2f} min)")
    return "\n".join(lines)


def main():
    from collector import config, db

    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=config.DB_PATH)
    ap.add_argument("--horizon", type=int, nargs="+", default=[30, 60])
    ap.add_argument("--truth", default="gps", choices=["gps", "feed"])
    ap.add_argument("--json", help="also write the results to this file")
    args = ap.parse_args()

    _, stops = config.load_targets()
    conn = db.connect(args.db)
    results = [run(conn, stops, h, args.truth) for h in args.horizon]
    for r in results:
        print(format_result(r))
    if args.json:
        with open(args.json, "w") as f:
            json.dump(results, f, indent=2)


if __name__ == "__main__":
    main()

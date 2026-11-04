#!/usr/bin/env python3
"""Projection where the lot size grows with profit: +0.01 lot for every $X of profit above the start
(and shrinks again if profit is given back). Start $500 at 0.01 lot. Same resampled real months as projection.py.

usage: python3 lot_growth.py xau_m1.pkl
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gold_scalper_bt import run  # noqa: E402
from period_report import params  # noqa: E402
from projection import simulate, lot_size  # noqa: E402


def month_lists(df, drop):
    months = [m for m in pd.period_range(df.month.min(), df.month.max(), freq="M") if str(m) not in drop]
    return [df.pnl[df.month == m].to_numpy() for m in months]


def main():
    m1 = pd.read_pickle(sys.argv[1])
    tr, _, _ = run(m1, params(), 1e6, quiet=True)
    df = pd.DataFrame(tr)
    df["month"] = pd.to_datetime(df.close_t * 60, unit="s").dt.to_period("M")
    sets = {"all months": month_lists(df, {"2025-08"}),
            "cautious (no Sep-Oct 2026)": month_lists(df, {"2025-08", "2026-09", "2026-10"})}
    modes = [("fixed 0.01 (reference)", "fixed")] + [(f"+0.01 lot per ${x} profit", ("profit", x)) for x in (500, 250, 100, 50)]
    rng = np.random.default_rng(42)
    start = 500.0
    for label, mt in sets.items():
        print(f"=== Start $500, {label} ===")
        print(f"{'lot growth':26s} {'yrs':>3s} | {'bad':>9s} {'typical':>10s} {'good':>11s} | {'P(<start)':>9s} {'P(out)':>6s} "
              f"{'med DD':>6s} {'95% DD':>6s} | {'typ max lot':>11s}")
        for name, mode in modes:
            for yrs in (1, 3, 5, 10):
                f, dead, dd, ml = simulate(mt, start, yrs, mode, 3000, rng)
                print(f"{name if yrs == 1 else '':26s} {yrs:3d} | {np.percentile(f, 10):9,.0f} {np.median(f):10,.0f} "
                      f"{np.percentile(f, 90):11,.0f} | {(f < start).mean() * 100:8.0f}% {dead.mean() * 100:5.0f}% "
                      f"{np.median(dd) * 100:5.0f}% {np.percentile(dd, 95) * 100:5.0f}% | {np.median(ml):11.2f}")
        print()
    # actual history replay
    for name, mode in modes:
        bal = start; ml = 0.01; ye = {}
        for x, m in zip(df.pnl, df.month):
            lots = lot_size(mode, bal, start); ml = max(ml, lots)
            bal += x * lots / 0.01; ye[m.year] = bal
        print(f"Actual 2020-2026 replay, {name:24s}: " + ", ".join(f"{y} ${v:,.0f}" for y, v in ye.items()) + f"  (max lot {ml:.2f})")


if __name__ == "__main__":
    main()

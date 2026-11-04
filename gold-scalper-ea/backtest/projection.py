#!/usr/bin/env python3
"""1/3/5/10-year scenarios for the planned setup by resampling REAL months of 2020-2026 trades.

Setup: RSI(2) H1 + daily-trend filter, $10 stop, $30 target, EMA5 exit, 24h, real raw-account costs.
Modes:  fixed    - always 0.01 lot (profit accumulates, size never changes)
        compound - 0.01 lot per $500 of balance (rounded down, minimum 0.01)
A path is "knocked out" if the balance falls below $60 (about the margin for 0.01 lot of gold at 1:100).
These are scenarios built from history, not predictions.

usage: python3 projection.py xau_m1.pkl
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gold_scalper_bt import run  # noqa: E402
from period_report import params  # noqa: E402

FLOOR = 60.0
PER_LOT_BAL = 500.0


def simulate(month_trades, start, years, mode, sims, rng):
    n_months = len(month_trades)
    finals = np.empty(sims); dead = np.zeros(sims, bool); mdd = np.empty(sims)
    for s in range(sims):
        bal = peak = start; worst = 0.0
        for m in rng.integers(0, n_months, 12 * years):
            for x in month_trades[m]:
                lots = 0.01 if mode == "fixed" else max(0.01, np.floor(bal / PER_LOT_BAL) * 0.01)
                bal += x * lots / 0.01
                peak = max(peak, bal); worst = max(worst, (peak - bal) / peak)
                if bal < FLOOR:
                    dead[s] = True
                    break
            if dead[s]:
                break
        finals[s] = bal; mdd[s] = worst
    return finals, dead, mdd


def main():
    m1 = pd.read_pickle(sys.argv[1])
    tr, _, _ = run(m1, params(), 1e6, quiet=True)
    df = pd.DataFrame(tr)
    df["month"] = pd.to_datetime(df.close_t * 60, unit="s").dt.to_period("M")
    months = pd.period_range(df.month.min(), df.month.max(), freq="M")
    months = [m for m in months if str(m) != "2025-08"]          # no data that month
    month_trades = [df.pnl[df.month == m].to_numpy() for m in months]
    print(f"resampling {len(month_trades)} real months, {len(df)} trades, avg ${df.pnl.sum() / len(month_trades):.2f}/month at 0.01 lot\n")
    rng = np.random.default_rng(42)
    for start in (500, 100):
        for mode in ("fixed", "compound"):
            print(f"Start ${start}, {'fixed 0.01 lot' if mode == 'fixed' else 'compounding (0.01 lot per $500)'}")
            print(f"  {'years':>5s} | {'bad (10th pct)':>14s} {'typical (median)':>16s} {'good (90th pct)':>15s} | "
                  f"{'P(below start)':>14s} {'P(knocked out)':>14s} {'median max DD':>13s}")
            for yrs in (1, 3, 5, 10):
                f, dead, dd = simulate(month_trades, start, yrs, mode, 4000, rng)
                print(f"  {yrs:5d} | {np.percentile(f, 10):14,.0f} {np.median(f):16,.0f} {np.percentile(f, 90):15,.0f} | "
                      f"{(f < start).mean() * 100:13.0f}% {dead.mean() * 100:13.0f}% {np.median(dd) * 100:12.0f}%")
            print()
    # actual history replayed with compounding from $500
    bal = 500.0; path = []
    for x, m in zip(df.pnl, df.month):
        bal += x * max(0.01, np.floor(bal / PER_LOT_BAL) * 0.01) / 0.01
        path.append((m, bal))
    yearly = pd.Series(dict(path)).groupby(lambda p: p.year).last()
    print("Actual 2020-2026 history, compounding from $500, balance at year end:",
          {int(k): round(v) for k, v in yearly.items()})


if __name__ == "__main__":
    main()

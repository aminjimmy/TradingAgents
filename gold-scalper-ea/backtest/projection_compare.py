#!/usr/bin/env python3
"""1/3/5/10-year scenarios (resampled real months) for the plan with and without extra filters.

usage: python3 projection_compare.py xau_m1.pkl [filter ...]     (default filter: macro_eur20)
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gold_scalper_bt import run  # noqa: E402
from period_report import params  # noqa: E402
from projection import simulate  # noqa: E402

START = 500.0
MODES = [("fixed 0.01", "fixed"), ("+0.01 per $500 profit", ("profit", 500)), ("+0.01 per $250 profit", ("profit", 250))]


def months_of(m1, extra):
    tr, _, _ = run(m1, params(sargs=dict(lo=10, filters=["daily_trend"] + extra)), 1e6, quiet=True)
    df = pd.DataFrame(tr)
    df["month"] = pd.to_datetime(df.close_t * 60, unit="s").dt.to_period("M")
    allm = [m for m in pd.period_range(df.month.min(), df.month.max(), freq="M") if str(m) != "2025-08"]
    full = [df.pnl[df.month == m].to_numpy() for m in allm]
    caut = [df.pnl[df.month == m].to_numpy() for m in allm if str(m) not in ("2026-09", "2026-10")]
    eq = df.pnl.cumsum()
    return full, caut, len(df), df.pnl.sum(), (eq.cummax() - eq).max()


def main():
    m1 = pd.read_pickle(sys.argv[1])
    extra = sys.argv[2:] or ["macro_eur20"]
    setups = {"plan (no dollar filter)": [], "plan + dollar filter (" + "+".join(extra) + ")": extra}
    data = {k: months_of(m1, v) for k, v in setups.items()}
    for k, (full, caut, n, net, dd) in data.items():
        print(f"{k}: {n} trades 2020-26, net ${net:+.0f}, max DD ${dd:.0f}, avg ${net / len(full):.2f}/month at 0.01 lot")
    for label, idx in (("ALL MONTHS (future like 2020-2026)", 0), ("CAUTIOUS (Sep-Oct 2026 removed)", 1)):
        print(f"\n=== Start ${START:.0f}, {label} — typical (median) balance [bad 10th pct / good 90th pct], median worst drawdown ===")
        print(f"{'setup':38s} {'lot growth':22s} | " + " | ".join(f"{y:>2d} yr{'s' if y > 1 else ' '}{'':22s}" for y in (1, 3, 5, 10)))
        for k in setups:
            mt = data[k][idx]
            for mname, mode in MODES:
                cells = []
                for yrs in (1, 3, 5, 10):
                    rng = np.random.default_rng(1000 + yrs)        # same random months for every setup
                    f, dead, dd, _ = simulate(mt, START, yrs, mode, 3000, rng)
                    cells.append(f"{np.median(f):>7,.0f} [{np.percentile(f, 10):>5,.0f}/{np.percentile(f, 90):>7,.0f}] {np.median(dd) * 100:3.0f}%")
                print(f"{k[:38]:38s} {mname:22s} | " + " | ".join(cells))


if __name__ == "__main__":
    main()

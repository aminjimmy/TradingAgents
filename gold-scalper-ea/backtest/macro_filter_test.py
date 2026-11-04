#!/usr/bin/env python3
"""Run the plan with macro filters through the full EA rules (0.01 lot, $10 SL, $30 TP, EMA5 exit, daily trend,
24h, raw costs) and report both halves, drawdown and the monthly profile.

usage: python3 macro_filter_test.py xau_m1.pkl
"""
import os
import sys
from multiprocessing import Pool

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gold_scalper_bt import run  # noqa: E402
from period_report import params  # noqa: E402

VARIANTS = ["(current plan)", "macro_usd20", "macro_eur20", "macro_ry20", "macro_usd_or_ry", "macro_usd_and_ry",
            "macro_vix5"]
M1 = {}


def job(v):
    extra = [] if v.startswith("(") else [v]
    tr, _, _ = run(M1["d"], params(sargs=dict(lo=10, filters=["daily_trend"] + extra)), 1e6, quiet=True)
    df = pd.DataFrame(tr)
    t = pd.to_datetime(df.close_t * 60, unit="s")
    y = t.dt.year
    p = df.pnl
    eq = p.cumsum()
    months = p.groupby(t.dt.to_period("M")).sum()
    months = months[months.index.astype(str) != "2025-08"]
    return v, dict(n=len(df), win=(p > 0).mean() * 100, pf=p[p > 0].sum() / -p[p < 0].sum(), net=p.sum(),
                   A=p[y < 2024].sum(), B=p[y >= 2024].sum(), dd=(eq.cummax() - eq).max(),
                   pos_years=int((p.groupby(y).sum() > 0).sum()), mwin=(months > 0).mean() * 100,
                   mavg=months.sum() / 81, mworst=months.min(), byyear=p.groupby(y).sum())


def main():
    M1["d"] = pd.read_pickle(sys.argv[1])
    with Pool(4) as pool:
        res = pool.map(job, VARIANTS)
    print(f"{'filter (on top of plan)':22s} | {'trades':>6s} {'win%':>5s} {'PF':>5s} {'net $':>6s} {'2020-23':>8s} {'2024-26':>8s} "
          f"{'maxDD':>6s} {'yrs+':>4s} | {'win mths':>8s} {'$/mth':>6s} {'worst mth':>9s}")
    for v, r in res:
        print(f"{v:22s} | {r['n']:6d} {r['win']:5.1f} {r['pf']:5.2f} {r['net']:+6.0f} {r['A']:+8.0f} {r['B']:+8.0f} "
              f"{r['dd']:6.0f} {r['pos_years']:3d}/7 | {r['mwin']:7.0f}% {r['mavg']:+6.2f} {r['mworst']:+9.0f}")
    for v, r in res:
        print(f"  {v:20s} by year: " + ", ".join(f"{k} {x:+.0f}" for k, x in r["byyear"].items()))


if __name__ == "__main__":
    main()

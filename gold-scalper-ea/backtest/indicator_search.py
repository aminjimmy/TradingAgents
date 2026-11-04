#!/usr/bin/env python3
"""Test extra indicators as confirmation filters on the user's preferred setup:
RSI(2) H1 mean reversion, 0.01 lot, $10 stop, $30 target, EMA5 exit, 24h, real raw-account costs.

Rule (fixed before running): keep an indicator only if net profit is higher than the baseline in BOTH
2020-2023 and 2024-2026 AND in at least 5 of the 7 calendar years.

usage: python3 indicator_search.py xau_m1.pkl [filter+filter ...]   # extra args = combinations to test
"""
import os
import sys
from multiprocessing import Pool

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gold_scalper_bt import Params, run  # noqa: E402
from real_spread_test import costs, ea  # noqa: E402

FILTERS = ["stochastic", "bollinger", "williams_r", "cci", "macd_turn", "adx_range", "adx_trend", "daily_trend",
           "stretch_atr", "rejection_wick", "rsi14", "two_closes", "ichimoku", "atr_regime", "london_ny_hours"]
M1 = {}


def params(filters, h4=False):
    kw = dict(ea("v1.10"), **costs("raw"))
    kw.update(fixed_lots=0.01, sl_atr=0.0, min_sl=10.0, rr=3.0, max_daily_loss_pct=0, use_session=False,
              use_trend=h4, sargs=dict(lo=10, filters=list(filters)))
    return Params(**kw)


def job(name):
    filters = [] if name == "baseline" else (["__h4"] if name == "h4_trend" else name.split("+"))
    h4 = "__h4" in filters
    filters = [f for f in filters if f != "__h4"]
    tr, _, _ = run(M1["d"], params(filters, h4), 1e6, quiet=True)
    if not tr:
        return name, None
    df = pd.DataFrame(tr)
    df["y"] = pd.to_datetime(df.open_t * 60, unit="s").dt.year
    pnl = df.pnl
    return name, dict(n=len(df), win=(pnl > 0).mean() * 100, pf=pnl[pnl > 0].sum() / -pnl[pnl < 0].sum(),
                      net=pnl.sum(), A=pnl[df.y < 2024].sum(), B=pnl[df.y >= 2024].sum(),
                      byyear=pnl.groupby(df.y).sum(), dd=(pnl.cumsum().cummax() - pnl.cumsum()).max())


def main():
    M1["d"] = pd.read_pickle(sys.argv[1])
    names = ["baseline"] + (sys.argv[2:] or FILTERS + ["h4_trend"])
    with Pool(4) as pool:
        res = dict(pool.map(job, names))
    b = res["baseline"]
    print(f"{'indicator filter':28s} | {'trades':>6s} {'win%':>5s} {'PF':>5s} {'net $':>7s} {'maxDD$':>6s} | "
          f"{'2020-23':>8s} {'2024-26':>8s} | yrs better | verdict")
    for n in names:
        r = res[n]
        if r is None:
            print(f"{n:28s} | no trades"); continue
        yrs = int((r["byyear"].reindex(b["byyear"].index, fill_value=0) > b["byyear"]).sum())
        keep = n != "baseline" and r["A"] > b["A"] and r["B"] > b["B"] and yrs >= 5
        print(f"{n:28s} | {r['n']:6d} {r['win']:5.1f} {r['pf']:5.2f} {r['net']:+7.0f} {r['dd']:6.0f} | "
              f"{r['A']:+8.0f} {r['B']:+8.0f} | {'' if n == 'baseline' else f'{yrs}/7':>10s} | "
              f"{'KEEP' if keep else ('' if n == 'baseline' else 'reject')}")


if __name__ == "__main__":
    main()

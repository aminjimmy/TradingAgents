#!/usr/bin/env python3
"""One-change-at-a-time refinements of the v1.10 RSI(2) engine, with REAL raw-account costs.

Acceptance rule (fixed before running): a change is kept only if it raises total R per year
in BOTH 2020-2023 and 2024-2026 versus the baseline, without lowering PF in either half.

usage: python3 refine_search.py xau_m1.pkl [round]
"""
import os
import sys
from multiprocessing import Pool

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gold_scalper_bt import Params, run  # noqa: E402
from real_spread_test import costs  # noqa: E402
from strategy_search import MR, tfs  # noqa: E402

BASE_S = dict(lo=10)
BASE_P = dict(MR, use_tf=tfs("H1"), use_trend=False)

ROUND1 = {
    "base":            ({}, {}),
    "add_M30":         ({}, dict(use_tf=tfs("M30", "H1"))),
    "add_M15_M30":     ({}, dict(use_tf=tfs("M15", "M30", "H1"))),
    "sl1.5":           ({}, dict(sl_atr=1.5)),
    "sl3":             ({}, dict(sl_atr=3.0)),
    "sl4":             ({}, dict(sl_atr=4.0)),
    "exit_rsi70":      (dict(exit_mode="rsi"), {}),
    "limit_exit":      (dict(limit_exit=True), {}),
    "turn":            (dict(turn=True), {}),
    "adx_max25":       (dict(adx_max=25), {}),
    "adx_max30":       (dict(adx_max=30), {}),
    "atr_band":        (dict(atr_band=(0.5, 2.0)), {}),
    "cost_gate4":      (dict(cost_k=4, cost=0.13), {}),
    "lo5":             (dict(lo=5), {}),
    "lo15":            (dict(lo=15), {}),
    "max_bars12":      ({}, dict(max_bars=12)),
    "max_bars48":      ({}, dict(max_bars=48)),
    "breakeven_1atr":  ({}, dict(be_r=0.5, be_lock=0.10)),
    "two_pos_per_tf":  ({}, dict(max_pos_tf=2)),
    "session_24h":     ({}, dict(use_session=False)),
    "session_9_20":    ({}, dict(sess_start=9, sess_end=20)),
}

M1 = {}
CFG = {}


def job(args):
    name, period = args
    sa, pa = CFG[name]
    d = M1["d"]
    d = d[d.index < "2024-01-01"] if period == "A" else d[d.index >= "2024-01-01"]
    years = (d.index[-1] - d.index[0]).days / 365.25
    kw = dict(BASE_P, **pa, sargs=dict(BASE_S, **sa), strategy="rsi2", **costs("raw"),
              fixed_lots=0.10, max_daily_loss_pct=0, max_trades_day=0, max_consec_losses=0)
    tr, _, _ = run(d, Params(**kw), 1e6, quiet=True)
    if not tr:
        return args, None
    r = np.array([t["r"] for t in tr]); pnl = np.array([t["pnl"] for t in tr])
    yr = pd.to_datetime(pd.Series([t["open_t"] for t in tr]) * 60, unit="s").dt.year
    pos_years = int((pd.Series(r).groupby(yr.values).sum() > 0).sum())
    return args, dict(n=len(r), avgR=r.mean(), totR_yr=r.sum() / years,
                      pf=pnl[pnl > 0].sum() / -pnl[pnl <= 0].sum(), pos_years=pos_years, n_years=yr.nunique())


def table(cfgs):
    CFG.clear(); CFG.update(cfgs)
    with Pool(4) as pool:
        res = dict(pool.map(job, [(n, p) for n in cfgs for p in "AB"]))
    b = (res[("base", "A")], res[("base", "B")])
    print(f"{'change':16s} | {'2020-23: n':>10s} {'avgR':>7s} {'R/yr':>6s} {'PF':>5s} | "
          f"{'2024-26: n':>10s} {'avgR':>7s} {'R/yr':>6s} {'PF':>5s} | yrs+  keep?")
    keep = []
    for n in cfgs:
        A, B = res[(n, "A")], res[(n, "B")]
        if not A or not B:
            print(f"{n:16s} no trades"); continue
        ok = n != "base" and A["totR_yr"] > b[0]["totR_yr"] and B["totR_yr"] > b[1]["totR_yr"] \
            and A["pf"] >= b[0]["pf"] and B["pf"] >= b[1]["pf"]
        if ok:
            keep.append(n)
        print(f"{n:16s} | {A['n']:10d} {A['avgR']:+7.3f} {A['totR_yr']:+6.1f} {A['pf']:5.2f} | "
              f"{B['n']:10d} {B['avgR']:+7.3f} {B['totR_yr']:+6.1f} {B['pf']:5.2f} | "
              f"{A['pos_years'] + B['pos_years']}/{A['n_years'] + B['n_years']}  {'KEEP' if ok else ''}")
    return keep


def main():
    M1["d"] = pd.read_pickle(sys.argv[1])
    print("kept:", table(ROUND1))


if __name__ == "__main__":
    main()

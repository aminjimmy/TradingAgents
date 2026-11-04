#!/usr/bin/env python3
"""Search for a more active ("aggressive") version of plan + daily trend + dollar filter (EURUSD proxy).
Fixed 0.01 lot, raw costs, 24h. Choice is made on 2020-2023 ONLY; 2024-2026 is shown for checking.

Selection rule (fixed in advance): among variants with PF >= 1.15 in 2020-23, pick the one with the highest
2020-23 profit per year. It must also be profitable in 2024-26 to be accepted.

usage: python3 small_account_search.py xau_m1.pkl
"""
import itertools
import os
import sys
from multiprocessing import Pool

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gold_scalper_bt import run  # noqa: E402
from period_report import params  # noqa: E402

M1 = {}


def variant_params(lo, pos, sl, tfset):
    use = {"M5": False, "M15": False, "M30": "M30" in tfset, "H1": True, "H4": False}
    return params(sargs=dict(lo=lo, filters=["daily_trend", "macro_eur20"]), max_pos_tf=pos, max_pos_total=pos * 2,
                  min_sl=float(sl), rr=30.0 / sl, use_tf=use)


def job(v):
    lo, pos, sl, tfset = v
    tr, _, _ = run(M1["d"], variant_params(lo, pos, sl, tfset), 1e6, quiet=True)
    df = pd.DataFrame(tr)
    y = pd.to_datetime(df.open_t * 60, unit="s").dt.year
    out = {}
    for h, mask, yrs in (("A", y < 2024, 4.0), ("B", y >= 2024, 2.82)):
        p = df.pnl[mask]
        eq = p.cumsum()
        out[h] = dict(n=len(p), tpy=len(p) / yrs, pf=p[p > 0].sum() / max(1e-9, -p[p < 0].sum()), net=p.sum(),
                      py=p.sum() / yrs, win=(p > 0).mean() * 100, dd=(eq.cummax() - eq).max())
    return v, out


def main():
    M1["d"] = pd.read_pickle(sys.argv[1])
    grid = list(itertools.product([10, 15, 20], [1, 2], [5, 7, 10], ["H1", "H1+M30"]))
    with Pool(4) as pool:
        res = dict(pool.map(job, grid))
    rows = sorted(res.items(), key=lambda kv: -kv[1]["A"]["py"])
    print(f"{'RSI lo':>6s} {'pos':>3s} {'SL$':>3s} {'TFs':7s} | {'2020-23: tr/yr':>14s} {'win%':>5s} {'PF':>5s} {'$/yr':>6s} {'maxDD':>6s} | "
          f"{'2024-26: tr/yr':>14s} {'win%':>5s} {'PF':>5s} {'$/yr':>6s} {'maxDD':>6s}")
    for (lo, pos, sl, tfs), r in rows:
        A, B = r["A"], r["B"]
        print(f"{lo:6d} {pos:3d} {sl:3d} {tfs:7s} | {A['tpy']:14.0f} {A['win']:5.1f} {A['pf']:5.2f} {A['py']:+6.0f} {A['dd']:6.0f} | "
              f"{B['tpy']:14.0f} {B['win']:5.1f} {B['pf']:5.2f} {B['py']:+6.0f} {B['dd']:6.0f}")
    ok = [(k, r) for k, r in rows if r["A"]["pf"] >= 1.15]
    if ok:
        k, r = ok[0]
        print(f"\nSELECTED on 2020-23 rule: RSI<{k[0]}, {k[1]} pos/TF, SL ${k[2]}, {k[3]} -> "
              f"2024-26 check: {r['B']['py']:+.0f} $/yr, PF {r['B']['pf']:.2f} ({'PASS' if r['B']['net'] > 0 else 'FAIL'})")


if __name__ == "__main__":
    main()

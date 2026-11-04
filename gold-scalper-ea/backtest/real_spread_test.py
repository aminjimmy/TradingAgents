#!/usr/bin/env python3
"""Re-run v1.00 and v1.10 with REAL time-of-day spreads measured from 176M Exness XAUUSD ticks (2024-2026).

usage: python3 real_spread_test.py xau_m1.pkl
Cost models:
  raw      real average spread for that year and UTC minute (Exness Raw Spread) + $7/lot round-turn commission
  standard same real intraday shape, scaled to average $0.30 (typical standard-account markup), no commission
  fixed30  flat $0.30 (the earlier runs, for comparison)
"""
import os
import sys
from multiprocessing import Pool

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gold_scalper_bt import Params, run, summary, load_spread_profile, spread_series  # noqa: E402
from strategy_search import MR, tfs  # noqa: E402

PROF = load_spread_profile(os.path.join(HERE, "spread_data", "exness_xauusd_avg_spread_by_minute_2024_2026.csv"))
M1 = {}


def costs(name):
    if name == "raw":
        return dict(spread_profile=PROF, commission_per_lot=7.0)
    if name == "standard":
        return dict(spread_profile=PROF, spread_scale=0.30 / float(np.nanmean(PROF.to_numpy())))
    return dict(spread=0.30)


def ea(version):
    if version == "v1.10":
        return dict(strategy="rsi2", sargs=dict(lo=10), use_tf=tfs("H1"), use_trend=False, risk_pct=0.5, **MR)
    return dict()  # v1.00 defaults


def job(args):
    version, cost, period, mode = args
    d = M1["d"]
    d = d[d.index < "2024-01-01"] if period == "2020-23" else d[d.index >= "2024-01-01"]
    kw = dict(ea(version), **costs(cost))
    if mode == "R":
        kw.update(fixed_lots=0.10, max_daily_loss_pct=0, max_trades_day=0, max_consec_losses=0)
        tr, _, _ = run(d, Params(**kw), 1e6, quiet=True)
        r = np.array([t["r"] for t in tr]); pnl = np.array([t["pnl"] for t in tr])
        return args, dict(n=len(r), avgR=r.mean(), pf=pnl[pnl > 0].sum() / -pnl[pnl <= 0].sum())
    tr, _, _ = run(d, Params(**kw), 10000, quiet=True)
    return args, summary(tr, 10000)


def main():
    M1["d"] = pd.read_pickle(sys.argv[1])
    sp = spread_series(M1["d"].index[M1["d"].index >= "2024-01-01"], Params(**costs("raw")))
    print(f"raw spread applied 2024-26: mean ${sp.mean():.3f}, median ${np.median(sp):.3f}, max ${sp.max():.3f}")
    jobs = [(v, c, per, m) for v in ("v1.10", "v1.00") for c in ("raw", "standard", "fixed30")
            for per in ("2020-23", "2024-26") for m in ("R", "acct")]
    with Pool(4) as pool:
        res = dict(pool.map(job, jobs))
    print(f"\n{'EA':6s} {'costs':9s} {'period':8s} | {'trades':>6s} {'avgR':>7s} {'PF':>5s} | {'$10k return':>11s} {'PF':>5s} {'maxDD':>6s}")
    for v in ("v1.10", "v1.00"):
        for c in ("raw", "standard", "fixed30"):
            for per in ("2020-23", "2024-26"):
                r, a = res[(v, c, per, "R")], res[(v, c, per, "acct")]
                print(f"{v:6s} {c:9s} {per:8s} | {r['n']:6d} {r['avgR']:+7.3f} {r['pf']:5.2f} | "
                      f"{a['ret']:+10.1f}% {a['pf']:5.2f} {a['mdd']:5.1f}%")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Full 2020-2026 compounding runs of v1.10 at several risk levels (real raw-account costs, all EA limits on),
plus a resampling Monte Carlo of each run.

usage: python3 risk_sizing.py xau_m1.pkl
"""
import os
import random
import sys
from multiprocessing import Pool

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gold_scalper_bt import Params, run, summary, write_trades_csv  # noqa: E402
from real_spread_test import costs, ea  # noqa: E402

M1 = {}


def mc(rets, sims=3000, seed=7):
    """Resample per-trade % returns (compounding) with 0-10% adverse stress."""
    rnd = random.Random(seed); n = len(rets); dds = []; fin = []
    for _ in range(sims):
        eq = peak = 1.0; mdd = 0.0
        for _ in range(n):
            x = rnd.choice(rets)
            x = x - abs(x) * rnd.uniform(0, 0.1) if x > 0 else x * rnd.uniform(1, 1.1)
            eq *= 1 + x; peak = max(peak, eq); mdd = max(mdd, 1 - eq / peak)
        dds.append(mdd); fin.append(eq)
    dds, fin = np.array(dds), np.array(fin)
    return np.median(dds) * 100, np.percentile(dds, 95) * 100, (fin < 1).mean() * 100, (dds > 0.2).mean() * 100


def job(args):
    risk, session = args
    kw = dict(ea("v1.10"), **costs("raw")); kw["risk_pct"] = risk; kw["use_session"] = session
    tr, bal, _ = run(M1["d"], Params(**kw), 10000, quiet=True)
    s = summary(tr, 10000)
    bal_before = 10000 + np.concatenate([[0], np.cumsum([t["pnl"] for t in tr])[:-1]])
    rets = [t["pnl"] / b for t, b in zip(tr, bal_before)]
    years = (M1["d"].index[-1] - M1["d"].index[0]).days / 365.25
    cagr = ((bal / 10000) ** (1 / years) - 1) * 100
    if risk == 0.5 and session:
        write_trades_csv(tr, "v110_final_trades.csv")
    return args, s, cagr, mc(rets)


def main():
    M1["d"] = pd.read_pickle(sys.argv[1])
    jobs = [(r, True) for r in (0.5, 1.0, 1.5, 2.0, 3.0)] + [(1.0, False)]
    with Pool(4) as pool:
        res = pool.map(job, jobs)
    print(f"{'risk':>5s} {'session':8s} | {'trades':>6s} {'total':>8s} {'per yr':>7s} {'PF':>5s} {'maxDD':>6s} | "
          f"MC: {'medDD':>6s} {'95%DD':>6s} {'P(DD>20%)':>9s} {'P(loss)':>7s}")
    for (r, sess), s, cagr, (md, d95, pl, p20) in res:
        print(f"{r:5.1f} {'09-23' if sess else '24h':8s} | {s['n']:6d} {s['ret']:+7.1f}% {cagr:+6.1f}% {s['pf']:5.2f} "
              f"{s['mdd']:5.1f}% | {md:5.1f}% {d95:5.1f}% {p20:8.0f}% {pl:6.0f}%")


if __name__ == "__main__":
    main()

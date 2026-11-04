#!/usr/bin/env python3
"""Stress tests for the final bot (v1.15 preset): parameter sensitivity, costs, execution delay,
broker time zone, and a bootstrap confidence interval. Fixed 0.01 lot, results in R (1R = $10 + costs).

usage: python3 robustness.py xau_m1.pkl
"""
import os
import sys
from multiprocessing import Pool

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gold_scalper_bt import Params, run  # noqa: E402
from real_spread_test import costs, ea, load_spread_profile  # noqa: E402

M1 = {}


def preset(lo=10, sl=10.0, tp=30.0, xema=5, d1=50, usd=20, spread_mult=1.0, slip=0.05, delay=0, **kw):
    c = costs("raw")
    p = dict(ea("v1.10"), **c)
    p.update(max_daily_loss_pct=0, fixed_lots=0.01, sl_atr=0.0, min_sl=sl, rr=tp / sl, use_session=False,
             spread_scale=spread_mult, slippage=slip, entry_delay_min=delay,
             sargs=dict(lo=lo, exit_ema=xema,
                        filters=[f"daily_trend:{d1}" if d1 != 50 else "daily_trend",
                                 f"macro_eur20:{usd}" if usd != 20 else "macro_eur20"]))
    p.update(kw)
    return Params(**p)


def job(args):
    name, kw, shift = args
    d = M1["d"]
    if shift:
        d = d.copy()
        d.index = d.index + pd.Timedelta(hours=shift)
    tr, _, _ = run(d, preset(**kw), 1e6, quiet=True)
    df = pd.DataFrame(tr)
    y = pd.to_datetime(df.open_t * 60, unit="s").dt.year
    p = df.pnl
    return name, dict(n=len(df), avgR=df.r.mean(), totR=df.r.sum(), A=df.r[y < 2024].sum(), B=df.r[y >= 2024].sum(),
                      pf=p[p > 0].sum() / -p[p < 0].sum(), yrs=int((df.r.groupby(y).sum() > 0).sum()))


def main():
    M1["d"] = pd.read_pickle(sys.argv[1])
    tests = [("PRESET", {}, 0)]
    tests += [(f"RSI level {v}", dict(lo=v), 0) for v in (8, 9, 11, 12)]
    tests += [(f"stop ${v} (target $30)", dict(sl=float(v)), 0) for v in (8, 9, 11, 12)]
    tests += [(f"target ${v}", dict(tp=float(v)), 0) for v in (20, 25, 35, 40)]
    tests += [(f"exit EMA{v}", dict(xema=v), 0) for v in (4, 6)]
    tests += [(f"daily trend EMA{v}", dict(d1=v), 0) for v in (30, 40, 60, 80)]
    tests += [(f"dollar lookback {v}d", dict(usd=v), 0) for v in (10, 15, 25, 30)]
    tests += [(f"spread x{v}", dict(spread_mult=v), 0) for v in (1.5, 2.0, 3.0)]
    tests += [(f"slippage ${v}/side", dict(slip=v), 0) for v in (0.10, 0.20)]
    tests += [(f"execution {v} min late", dict(delay=v), 0) for v in (1, 5, 15)]
    tests += [(f"broker clock {v:+d}h", {}, v) for v in (-2, -1, 1, 2)]
    with Pool(4) as pool:
        res = pool.map(job, tests)
    base = res[0][1]
    print(f"{'test':26s} | {'trades':>6s} {'avgR':>7s} {'PF':>5s} {'total R':>8s} {'2020-23':>8s} {'2024-26':>8s} {'yrs+':>5s} | vs preset")
    for name, r in res:
        rel = r["totR"] / base["totR"] * 100
        print(f"{name:26s} | {r['n']:6d} {r['avgR']:+7.3f} {r['pf']:5.2f} {r['totR']:+8.1f} {r['A']:+8.1f} {r['B']:+8.1f} "
              f"{r['yrs']:3d}/7 | {rel:5.0f}%")

    # bootstrap confidence interval on the preset's per-trade R (blocks of 20 trades to respect clustering)
    tr, _, _ = run(M1["d"], preset(), 1e6, quiet=True)
    r = pd.DataFrame(tr).r.to_numpy()
    rng = np.random.default_rng(5)
    blocks = [r[i:i + 20] for i in range(0, len(r), 20)]
    boots = np.array([np.concatenate([blocks[j] for j in rng.integers(0, len(blocks), len(blocks))]).mean()
                      for _ in range(5000)])
    print(f"\nBootstrap (5,000 x block resample): avg R {r.mean():+.3f}, 90% CI [{np.percentile(boots, 5):+.3f}, "
          f"{np.percentile(boots, 95):+.3f}], P(avg R <= 0) = {(boots <= 0).mean() * 100:.1f}%")
    r_ex26 = pd.DataFrame(tr)
    r_ex26 = r_ex26[pd.to_datetime(r_ex26.open_t * 60, unit="s").dt.year < 2026].r.to_numpy()
    blocks = [r_ex26[i:i + 20] for i in range(0, len(r_ex26), 20)]
    boots = np.array([np.concatenate([blocks[j] for j in rng.integers(0, len(blocks), len(blocks))]).mean()
                      for _ in range(5000)])
    print(f"Without 2026: avg R {r_ex26.mean():+.3f}, 90% CI [{np.percentile(boots, 5):+.3f}, {np.percentile(boots, 95):+.3f}], "
          f"P(avg R <= 0) = {(boots <= 0).mean() * 100:.1f}%")


if __name__ == "__main__":
    main()

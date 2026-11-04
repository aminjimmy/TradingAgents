#!/usr/bin/env python3
"""Compare entry engines with fixed lots (results in R, no compounding, no daily limits).

usage: python3 strategy_search.py xau_m1.pkl is    # design period 2020-2023
       python3 strategy_search.py xau_m1.pkl oos NAME [NAME...]   # untouched 2024-2026
"""
import os
import sys
from multiprocessing import Pool

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gold_scalper_bt import Params, run  # noqa: E402

ALL = ("M5", "M15", "M30", "H1")


def tfs(*on):
    return {k: k in on for k in ALL}


# management presets
MR = dict(sl_atr=2.0, rr=3.0, be_r=0, trail_start_r=0, max_bars=24, close_on_opposite=False)  # mean reversion
TF_ = dict(sl_atr=2.0, rr=10.0, be_r=0, trail_start_r=1.0, trail_atr=3.0, max_bars=0)         # trend following
BO = dict(sl_atr=1.5, rr=2.0, be_r=1.0, trail_start_r=1.5, trail_atr=1.5, max_bars=32)        # breakout

CONFIGS = {
    # opening-range breakouts (M15 bars)
    "orb_london":        ("orb", dict(range_start=2, range_end=10, window_end=14), tfs("M15"), dict(BO, use_trend=False)),
    "orb_london_trend":  ("orb", dict(range_start=2, range_end=10, window_end=14), tfs("M15"), dict(BO, use_trend=True)),
    "orb_ny":            ("orb", dict(range_start=10, range_end=16.5, window_end=19), tfs("M15"), dict(BO, use_trend=False)),
    "orb_ny_trend":      ("orb", dict(range_start=10, range_end=16.5, window_end=19), tfs("M15"), dict(BO, use_trend=True)),
    # RSI(2) pullbacks
    "rsi2_M15":          ("rsi2", dict(lo=10), tfs("M15"), dict(MR, use_trend=False)),
    "rsi2_M30":          ("rsi2", dict(lo=10), tfs("M30"), dict(MR, use_trend=False)),
    "rsi2_H1":           ("rsi2", dict(lo=10), tfs("H1"), dict(MR, use_trend=False)),
    "rsi2_H1_lo5":       ("rsi2", dict(lo=5), tfs("H1"), dict(MR, use_trend=False)),
    "rsi2_M30_H1_htf":   ("rsi2", dict(lo=10), tfs("M30", "H1"), dict(MR, use_trend=True)),
    # round 2: RSI(2) refinements (decided after round 1, still 2020-2023 only)
    "rsi2_H1_sl3":       ("rsi2", dict(lo=10), tfs("H1"), dict(MR, sl_atr=3.0, use_trend=False)),
    "rsi2_H1_sl3_48":    ("rsi2", dict(lo=10), tfs("H1"), dict(MR, sl_atr=3.0, max_bars=48, use_trend=False)),
    "rsi2_H1_x3":        ("rsi2", dict(lo=10, exit_ema=3), tfs("H1"), dict(MR, use_trend=False)),
    "rsi2_H1_x10":       ("rsi2", dict(lo=10, exit_ema=10), tfs("H1"), dict(MR, use_trend=False)),
    "rsi2_H1_lo20":      ("rsi2", dict(lo=20), tfs("H1"), dict(MR, use_trend=False)),
    "rsi2_H1_htf":       ("rsi2", dict(lo=10), tfs("H1"), dict(MR, use_trend=True)),
    "rsi2_H1_sl3_htf":   ("rsi2", dict(lo=10), tfs("H1"), dict(MR, sl_atr=3.0, use_trend=True)),
    "rsi2_H1_zero_cost": ("rsi2", dict(lo=10), tfs("H1"), dict(MR, use_trend=False, spread=0.0, slippage=0.0)),
    # Donchian trend breakouts
    "donch20_M30":       ("donchian", dict(n=20), tfs("M30"), dict(TF_, use_trend=False)),
    "donch20_H1":        ("donchian", dict(n=20), tfs("H1"), dict(TF_, use_trend=False)),
    "donch55_H1":        ("donchian", dict(n=55), tfs("H1"), dict(TF_, use_trend=False)),
    "donch20_H1_htf":    ("donchian", dict(n=20), tfs("H1"), dict(TF_, use_trend=True)),
    # baselines: random entries with the same exits
    "rand_MR_H1":        ("random", dict(prob=0.03, mimic_exit_ema=5), tfs("H1"), dict(MR, use_trend=False)),
    "rand_TF_H1":        ("random", dict(prob=0.03), tfs("H1"), dict(TF_, use_trend=False)),
    "rand_TF_H1_htf":    ("random", dict(prob=0.03), tfs("H1"), dict(TF_, use_trend=True)),
    "rand_BO_M15":       ("random", dict(prob=0.01), tfs("M15"), dict(BO, use_trend=False)),
    "rand_long_TF_H1":   ("random", dict(prob=0.03, side=1), tfs("H1"), dict(TF_, use_trend=False)),
}

DATA = {}


def stats(tr):
    if not tr:
        return dict(n=0)
    df = pd.DataFrame(tr)
    pnl, r = df.pnl.to_numpy(), df.r.to_numpy()
    out = dict(n=len(df), avgR=r.mean(), pf=pnl[pnl > 0].sum() / max(1e-9, -pnl[pnl <= 0].sum()),
               win=(pnl > 0).mean() * 100,
               longR=df.r[df.dir > 0].mean() if (df.dir > 0).any() else np.nan, nl=int((df.dir > 0).sum()),
               shortR=df.r[df.dir < 0].mean() if (df.dir < 0).any() else np.nan, ns=int((df.dir < 0).sum()))
    yr = pd.to_datetime(df.open_t * 60, unit="s").dt.year
    out["years"] = " ".join(f"{y}:{v:+.2f}" for y, v in df.r.groupby(yr).mean().items())
    return out


def job(name):
    strat, sargs, use_tf, ov = CONFIGS[name]
    p = Params(strategy=strat, sargs=sargs, use_tf=use_tf, fixed_lots=0.10, max_daily_loss_pct=0,
               max_trades_day=0, max_consec_losses=0, max_pos_total=4, **ov)
    tr, _, _ = run(DATA["m1"], p, 1e6, quiet=True)
    return name, stats(tr)


def main():
    m1 = pd.read_pickle(sys.argv[1])
    mode = sys.argv[2]
    DATA["m1"] = m1[m1.index < "2024-01-01"] if mode == "is" else m1[m1.index >= "2024-01-01"]
    names = sys.argv[3:] or list(CONFIGS)
    with Pool(4) as pool:
        res = pool.map(job, names)
    print(f"{'config':18s} {'n':>6s} {'avgR':>7s} {'PF':>5s} {'win%':>5s} {'longR(n)':>14s} {'shortR(n)':>14s}  per-year avgR")
    for name, s in res:
        if not s["n"]:
            print(f"{name:18s} no trades")
            continue
        print(f"{name:18s} {s['n']:6d} {s['avgR']:+7.3f} {s['pf']:5.2f} {s['win']:5.1f} "
              f"{s['longR']:+7.3f}({s['nl']:5d}) {s['shortR']:+7.3f}({s['ns']:5d})  {s['years']}")


if __name__ == "__main__":
    main()

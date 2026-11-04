#!/usr/bin/env python3
"""$100 account plans for the plan + daily trend + dollar filter (EURUSD proxy), $10 stop / $30 target, 24h.

Sizing modes:
  fixed 0.01            always 0.01 lot (needs 0.01 minimum lot)
  risk X%               lots = X% of balance / $10 stop, in 0.001-lot steps, min 0.001 (needs a 0.001-step symbol)
Scenarios: resampled real months (3,000 paths), plus the actual history replayed from Jan 2020 and Jan 2024.
"Knocked out" = balance below $20 (0.001-lot margin) or below $60 for fixed 0.01 lot.

usage: python3 hundred_dollar.py xau_m1.pkl
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gold_scalper_bt import run  # noqa: E402
from period_report import params  # noqa: E402

START, SL = 100.0, 10.0


def lots_for(mode, bal):
    if mode == "fixed":
        return 0.01
    lots = np.floor(bal * mode / 100 / SL * 0.01 / 0.001 + 1e-9) * 0.001
    return max(0.001, lots)


def path(trades, mode):
    bal, peak, worst = START, START, 0.0
    floor = 60.0 if mode == "fixed" else 20.0
    for x in trades:
        bal += x * lots_for(mode, bal) / 0.01
        peak = max(peak, bal); worst = max(worst, 1 - bal / peak)
        if bal < floor:
            return bal, True, worst
    return bal, False, worst


def main():
    m1 = pd.read_pickle(sys.argv[1])
    configs = {"core (RSI<10)": 10, "active (RSI<15)": 15}
    modes = [("fixed 0.01 lot", "fixed"), ("risk 2%", 2.0), ("risk 3%", 3.0), ("risk 5%", 5.0), ("risk 8%", 8.0)]
    for cname, lo in configs.items():
        tr, _, _ = run(m1, params(sargs=dict(lo=lo, filters=["daily_trend", "macro_eur20"])), 1e6, quiet=True)
        df = pd.DataFrame(tr)
        t = pd.to_datetime(df.close_t * 60, unit="s")
        df["month"] = t.dt.to_period("M")
        months = [df.pnl[df.month == m].to_numpy() for m in pd.period_range(df.month.min(), df.month.max(), freq="M")
                  if str(m) != "2025-08"]
        print(f"\n##### {cname}: {len(df)} trades 2020-26 ({len(df) / 6.8:.0f}/yr), ${df.pnl.sum():+.0f} at 0.01 lot")
        print(f"{'sizing':16s} {'yrs':>3s} | {'typical':>8s} {'bad 10%':>8s} {'good 90%':>9s} | {'P(loss)':>7s} {'P(<$50)':>7s} "
              f"{'P(out)':>6s} | {'med worst DD':>12s}")
        for mname, mode in modes:
            for yrs in (1, 3, 5):
                rng = np.random.default_rng(7 + yrs)
                fin, out, dds = [], 0, []
                for _ in range(3000):
                    seq = np.concatenate([months[i] for i in rng.integers(0, len(months), 12 * yrs)])
                    b, dead, dd = path(seq, mode)
                    fin.append(b); out += dead; dds.append(dd)
                fin = np.array(fin)
                print(f"{mname if yrs == 1 else '':16s} {yrs:3d} | {np.median(fin):8,.0f} {np.percentile(fin, 10):8,.0f} "
                      f"{np.percentile(fin, 90):9,.0f} | {(fin < START).mean() * 100:6.0f}% {(fin < 50).mean() * 100:6.0f}% "
                      f"{out / 30:5.0f}% | {np.median(dds) * 100:11.0f}%")
        for start in ("2020-01-01", "2024-01-01"):
            seq = df.pnl[t >= start].to_numpy()
            txt = []
            for mname, mode in modes:
                b, dead, dd = path(seq, mode)
                txt.append(f"{mname}: ${b:,.0f}{' (knocked out)' if dead else ''} DD {dd * 100:.0f}%")
            print(f"actual history from {start[:4]}: " + " | ".join(txt))


if __name__ == "__main__":
    main()

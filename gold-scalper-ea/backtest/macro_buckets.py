#!/usr/bin/env python3
"""Do the plan's trades do better when the dollar / real yields / VIX are moving in gold's favour?
Splits the plan's real trades (0.01 lot, $10 SL, $30 TP, EMA5 exit, daily trend, 24h, raw costs) by the
previous US day's macro readings, separately for 2020-2023 and 2024-2026.

usage: python3 macro_buckets.py xau_m1.pkl
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gold_scalper_bt import run  # noqa: E402
from ml_features import macro_features  # noqa: E402
from period_report import params  # noqa: E402


def main():
    m1 = pd.read_pickle(sys.argv[1])
    tr, _, _ = run(m1, params(), 1e6, quiet=True)
    df = pd.DataFrame(tr)
    t = pd.DatetimeIndex(pd.to_datetime(df.open_t * 60, unit="s"))
    mf = macro_features(t.floor("h")).reset_index(drop=True)
    df = pd.concat([df, mf], axis=1)
    df["half"] = np.where(t.year < 2024, "2020-23", "2024-26")
    d = df["dir"]
    tests = {
        "dollar 20d falling (for longs) / rising (for shorts)": np.sign(df.dxy_chg20) == -d,
        "dollar below its 50d average (longs) / above (shorts)": np.sign(df.dxy_vs_ema50) == -d,
        "real yields 20d falling (longs) / rising (shorts)": np.sign(df.real_yield_chg20) == -d,
        "nominal 10y yields 20d falling (longs) / rising (shorts)": np.sign(df.nominal10_chg20) == -d,
        "VIX rose over 5 days": df.vix_chg5 > 0,
        "VIX above 20": df.vix > 20,
        "within 5 days after a Fed meeting": df.days_since_fomc <= 5,
    }
    print(f"{'condition':58s} | {'half':7s} | {'when TRUE: n  $/trade  PF':>27s} | {'when FALSE: n  $/trade  PF':>28s}")
    for name, cond in tests.items():
        for h in ("2020-23", "2024-26"):
            row = []
            for flag in (True, False):
                p = df.pnl[(cond == flag) & (df.half == h)]
                pf = p[p > 0].sum() / max(1e-9, -p[p < 0].sum())
                row.append(f"{len(p):5d} {p.mean():+7.2f} {pf:5.2f}")
            print(f"{name if h == '2020-23' else '':58s} | {h} | {row[0]:>27s} | {row[1]:>28s}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Is v1.10 better than luck? Compare its average R with N random-entry runs that use the SAME
direction rule (long above EMA200 / short below), SAME exits (EMA5 cross, 2xATR stop, 24-bar limit),
SAME sessions and REAL raw-account costs, with entry rate matched to the strategy's trade count.

usage: python3 permutation_test.py xau_m1.pkl [N]
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

M1 = {}
BASE = dict(MR, use_tf=tfs("H1"), use_trend=False, fixed_lots=0.10, max_daily_loss_pct=0,
            max_trades_day=0, max_consec_losses=0)


def avg_r(strategy, sargs, period):
    d = M1["d"]
    d = d if period == "all" else (d[d.index < "2024-01-01"] if period == "A" else d[d.index >= "2024-01-01"])
    tr, _, _ = run(d, Params(strategy=strategy, sargs=sargs, **BASE, **costs("raw")), 1e6, quiet=True)
    return np.mean([t["r"] for t in tr]), len(tr)


def rnd(args):
    seed, prob, period = args
    return avg_r("random", dict(prob=prob, seed=seed, trend_side=200, mimic_exit_ema=5), period)


def main():
    M1["d"] = pd.read_pickle(sys.argv[1])
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 200
    for period, label in (("all", "2020-2026"), ("A", "2020-2023"), ("B", "2024-2026")):
        real, nt = avg_r("rsi2", dict(lo=10), period)
        _, nr = rnd((0, 0.05, period))
        prob = 0.05 * nt / max(nr, 1)     # match trade count
        with Pool(4) as pool:
            res = pool.map(rnd, [(s, prob, period) for s in range(1, n + 1)])
        rs = np.array([r for r, _ in res])
        p = (np.sum(rs >= real) + 1) / (len(rs) + 1)
        print(f"{label}: v1.10 avgR {real:+.3f} ({nt} trades) | random: mean {rs.mean():+.3f}, "
              f"95th pct {np.percentile(rs, 95):+.3f}, max {rs.max():+.3f} (avg {np.mean([k for _, k in res]):.0f} trades) "
              f"| p-value {p:.3f}")


if __name__ == "__main__":
    main()

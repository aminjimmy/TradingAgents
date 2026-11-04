#!/usr/bin/env python3
"""Parity test: the live bot's decide_entry() must give the same signals as the backtester on history.
Replays 2024-01 .. 2026-09 H1 bars bar-by-bar, feeding the live function only the data it would have had
(last 2,500 H1 closes, last 200 completed days, FRED EURUSD up to the previous day).

usage: python3 parity_test.py xau_m1.pkl
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "backtest"))
from oanda_bot import decide_entry  # noqa: E402
from gold_scalper_bt import Params, resample  # noqa: E402
from ml_features import _series  # noqa: E402
from strategies import sig_rsi2  # noqa: E402


def main():
    m1 = pd.read_pickle(sys.argv[1])
    h1 = resample(m1, 60)
    p = Params(strategy="rsi2", sargs=dict(lo=10, filters=["daily_trend", "macro_eur20:20"]),
               use_tf={"H1": True})
    ref = pd.Series(sig_rsi2(h1, p, "H1")["dir"].to_numpy(), index=h1.index)
    closes = h1["close"]
    d1 = closes.resample("1D").last().dropna()
    eur = _series("DEXUSEU")
    test = h1.index[(h1.index >= "2024-01-02") & (h1.index < "2026-09-20")]
    pos = {t: i for i, t in enumerate(h1.index)}
    live = {}
    for t in test:
        i = pos[t]
        day = t.normalize()
        e = eur[eur.index <= day - pd.Timedelta(days=1)]
        live[t] = decide_entry(closes.iloc[max(0, i - 2499): i + 1], d1[d1.index < day].iloc[-200:], e.iloc[-60:])[0]
    live = pd.Series(live)
    r = ref.reindex(live.index)
    agree = (live == r)
    sig = (live != 0) | (r != 0)
    print(f"bars compared: {len(live)}, signal bars (either side): {int(sig.sum())}, "
          f"live signals {int((live != 0).sum())}, backtester signals {int((r != 0).sum())}")
    print(f"agreement on signal bars: {agree[sig].mean() * 100:.1f}%  (all bars: {agree.mean() * 100:.2f}%)")
    diff = pd.DataFrame({"live": live, "backtest": r})[~agree]
    if len(diff):
        print("mismatches (first 10):"); print(diff.head(10).to_string())


if __name__ == "__main__":
    main()

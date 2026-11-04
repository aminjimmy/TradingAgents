#!/usr/bin/env python3
"""Does the RSI(2) H1 mean-reversion strategy work on other commodities? Instrument-neutral version of the
plan (ATR-based stop so it fits any price scale): RSI(2)<10 above EMA200 (mirror for shorts), daily-trend
filter, SL 2xATR, TP 6xATR, EMA5 exit, 24 bars max, 24h. Results in R (multiples of the risk per trade)
with a fixed lot, plus a $10k account at 0.5% risk.

usage: python3 multi_asset_test.py SYMBOL data.pkl spread slippage contract [extra filters...]
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gold_scalper_bt import Params, run, summary  # noqa: E402
from strategy_search import MR, tfs  # noqa: E402


def params(spread, slip, contract, filters, **kw):
    p = dict(MR, strategy="rsi2", use_tf=tfs("H1"), use_trend=False, use_session=False, spread=spread,
             slippage=slip, contract=contract, min_sl=spread * 2, max_spread=spread * 5,
             sargs=dict(lo=10, filters=filters))
    p.update(kw)
    return Params(**p)


def main():
    sym, path, spread, slip, contract = sys.argv[1], sys.argv[2], *map(float, sys.argv[3:6])
    m1 = pd.read_pickle(path)
    m1 = m1[m1.index >= "2019-06-01"]
    sets = {"plan (daily trend)": ["daily_trend"], "plan + dollar filter": ["daily_trend", "macro_eur20"],
            "no daily trend": []}
    print(f"{sym}: {m1.index[0].date()} .. {m1.index[-1].date()}, spread {spread}, slippage {slip}")
    print(f"{'setup':24s} | {'trades':>6s} {'win%':>5s} {'avgR':>7s} {'PF':>5s} | {'2020-23 avgR':>12s} {'2024-26 avgR':>12s} | "
          f"{'$10k @0.5%':>10s} {'maxDD':>6s} | yearly R")
    for name, fl in sets.items():
        tr, _, _ = run(m1, params(spread, slip, contract, fl, fixed_lots=0.01, max_daily_loss_pct=0,
                                  max_trades_day=0, max_consec_losses=0), 1e9, quiet=True)
        df = pd.DataFrame(tr)
        df = df[pd.to_datetime(df.open_t * 60, unit="s") >= "2020-01-01"]
        y = pd.to_datetime(df.open_t * 60, unit="s").dt.year
        p = df.pnl
        pf = p[p > 0].sum() / -p[p < 0].sum()
        tr2, _, _ = run(m1[m1.index >= "2020-01-01"], params(spread, slip, contract, fl, risk_pct=0.5), 10000, quiet=True)
        s2 = summary(tr2, 10000)
        yr = df.r.groupby(y).sum().round(1)
        print(f"{name:24s} | {len(df):6d} {(p > 0).mean() * 100:5.1f} {df.r.mean():+7.3f} {pf:5.2f} | "
              f"{df.r[y < 2024].mean():+12.3f} {df.r[y >= 2024].mean():+12.3f} | {s2['ret']:+9.1f}% {s2['mdd']:5.1f}% | "
              + " ".join(f"{k}:{v:+.1f}" for k, v in yr.items()))


if __name__ == "__main__":
    main()

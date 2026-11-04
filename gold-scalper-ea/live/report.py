#!/usr/bin/env python3
"""Forward-test report: pulls the bot's trades (tag claude-gold) from the OANDA practice account and shows
results, R multiples, and what a $100 account risking 5% per trade would have done with the same trades.
Compare with the backtest: avg R about +0.05..+0.10, ~3 trades/week, win rate 55-66%.

usage: python3 report.py [--risk 5] [--start 100]
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from oanda_bot import INSTRUMENT, TAG, Oanda  # noqa: E402


def main():
    risk = float(sys.argv[sys.argv.index("--risk") + 1]) if "--risk" in sys.argv else 5.0
    start = float(sys.argv[sys.argv.index("--start") + 1]) if "--start" in sys.argv else 100.0
    stop = float(os.environ.get("STOP_USD", "10"))
    api = Oanda()
    closed = api.get(f"/accounts/{api.acct}/trades", state="CLOSED", instrument=INSTRUMENT, count=500)["trades"]
    ours = [t for t in closed if t.get("clientExtensions", {}).get("tag") == TAG]
    opened = [t for t in api.get(f"/accounts/{api.acct}/openTrades")["trades"]
              if t.get("clientExtensions", {}).get("tag") == TAG]
    if not ours:
        print(f"No closed trades yet. Open positions: {len(opened)}")
        return
    df = pd.DataFrame([dict(id=t["id"], open=pd.Timestamp(t["openTime"]), close=pd.Timestamp(t["closeTime"]),
                            units=float(t["initialUnits"]), entry=float(t["price"]),
                            exit=float(t.get("averageClosePrice", "nan")), pnl=float(t["realizedPL"]) +
                            float(t.get("financing", 0))) for t in ours]).sort_values("close")
    df["R"] = df.pnl / (df.units.abs() * stop)
    eq, peak, dd = start, start, 0.0
    for r in df.R:
        eq *= 1 + risk / 100 * r; peak = max(peak, eq); dd = max(dd, 1 - eq / peak)
    weeks = max(1.0, (df.close.max() - df.open.min()).days / 7)
    print(f"Forward test since {df.open.min():%Y-%m-%d}: {len(df)} closed trades ({len(df) / weeks:.1f}/week), "
          f"open now: {len(opened)}")
    print(f"  win rate {(df.pnl > 0).mean() * 100:.0f}% | avg R {df.R.mean():+.3f} | total {df.R.sum():+.2f}R | "
          f"P/L on practice account ${df.pnl.sum():+.2f}")
    print(f"  ${start:.0f} account at {risk:.0f}% risk with these trades: ${eq:.2f} (worst drawdown {dd * 100:.0f}%)")
    print(f"  backtest expectation: avg R about +0.05..+0.10, about 3 trades/week, win rate 55-66%")
    print(df.tail(15)[["open", "close", "units", "entry", "exit", "pnl", "R"]].round(3).to_string(index=False))


if __name__ == "__main__":
    main()

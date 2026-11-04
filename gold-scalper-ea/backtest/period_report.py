#!/usr/bin/env python3
"""Daily / weekly / monthly profit profile of the user's scalping setup, with optional $ daily target / stop.

Setup: RSI(2) H1 mean reversion + daily-trend filter, 0.01 lot, $10 stop, $30 target, EMA5 exit, 24h,
real raw-account costs, 2020-2026.

usage: python3 period_report.py xau_m1.pkl
"""
import os
import sys
from multiprocessing import Pool

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gold_scalper_bt import Params, run  # noqa: E402
from real_spread_test import costs, ea  # noqa: E402

M1 = {}
VARIANTS = {
    "no daily target/stop":       dict(),
    "target $10/day":             dict(daily_target_usd=10),
    "target $20/day":             dict(daily_target_usd=20),
    "target $30/day":             dict(daily_target_usd=30),
    "stop -$20/day":              dict(daily_loss_usd=20),
    "target $20 + stop -$20":     dict(daily_target_usd=20, daily_loss_usd=20),
}


def params(**extra):
    kw = dict(ea("v1.10"), **costs("raw"))
    kw.update(fixed_lots=0.01, sl_atr=0.0, min_sl=10.0, rr=3.0, max_daily_loss_pct=0, use_session=False,
              sargs=dict(lo=10, filters=["daily_trend"]))
    kw.update(extra)
    return Params(**kw)


def periods(tr, start, end):
    df = pd.DataFrame(tr)
    t = pd.to_datetime(df.close_t * 60, unit="s")
    s = pd.Series(df.pnl.to_numpy(), index=t)
    days = s.groupby(s.index.normalize()).sum()                      # days with at least one closed trade
    bdays = pd.bdate_range(start.normalize(), end.normalize())
    weeks = s.resample("W-FRI").sum()
    weeks = weeks.reindex(pd.date_range(weeks.index[0], weeks.index[-1], freq="W-FRI"), fill_value=0)
    weeks = weeks[weeks.index.to_period("M").astype(str) != "2025-08"]  # no data for Aug 2025
    months = s.resample("ME").sum()
    months = months[months.index.to_period("M").astype(str) != "2025-08"]
    return days, len(bdays), weeks, months


def describe(x):
    return dict(n=len(x), pos=(x > 0).mean() * 100, avg=x.mean(), med=x.median(), best=x.max(), worst=x.min())


def job(name):
    d = M1["d"]
    tr, _, _ = run(d, params(**VARIANTS[name]), 1e6, quiet=True)
    days, nb, weeks, months = periods(tr, d.index[0], d.index[-1])
    pnl = np.array([t["pnl"] for t in tr])
    yrs = pd.to_datetime(pd.Series([t["open_t"] for t in tr]) * 60, unit="s").dt.year
    A, B = pnl[(yrs < 2024).to_numpy()].sum(), pnl[(yrs >= 2024).to_numpy()].sum()
    eq = np.cumsum(pnl)
    return name, dict(n=len(tr), net=pnl.sum(), A=A, B=B, dd=(np.maximum.accumulate(eq) - eq).max(),
                      days=describe(days), active=len(days) / nb * 100, weeks=describe(weeks),
                      months=describe(months), monthly=months, yearly=pd.Series(pnl).groupby(yrs.values).sum())


def main():
    M1["d"] = pd.read_pickle(sys.argv[1])
    with Pool(4) as pool:
        res = dict(pool.map(job, VARIANTS))
    print(f"{'variant':24s} | {'trades':>6s} {'net $':>6s} {'2020-23':>7s} {'2024-26':>7s} {'maxDD':>6s} | "
          f"{'win days':>8s} {'win wks':>7s} {'win mths':>8s} | {'avg/day':>7s} {'avg/wk':>7s} {'avg/mth':>7s} | "
          f"{'worst day':>9s} {'worst wk':>8s} {'worst mth':>9s}")
    for n, r in res.items():
        print(f"{n:24s} | {r['n']:6d} {r['net']:+6.0f} {r['A']:+7.0f} {r['B']:+7.0f} {r['dd']:6.0f} | "
              f"{r['days']['pos']:7.0f}% {r['weeks']['pos']:6.0f}% {r['months']['pos']:7.0f}% | "
              f"{r['days']['avg']:+7.2f} {r['weeks']['avg']:+7.2f} {r['months']['avg']:+7.2f} | "
              f"{r['days']['worst']:+9.0f} {r['weeks']['worst']:+8.0f} {r['months']['worst']:+9.0f}")
    b = res["no daily target/stop"]
    print(f"\nBase setup detail: trading on {b['active']:.0f}% of weekdays; "
          f"best day {b['days']['best']:+.0f}, best week {b['weeks']['best']:+.0f}, best month {b['months']['best']:+.0f}; "
          f"median day {b['days']['med']:+.2f}, median week {b['weeks']['med']:+.2f}, median month {b['months']['med']:+.2f}")
    print("By year ($):", b["yearly"].round(0).to_dict())
    m = b["monthly"]
    print("Monthly P&L by year ($):")
    tab = pd.DataFrame({"y": m.index.year, "m": m.index.month, "v": m.values}).pivot(index="y", columns="m", values="v")
    print(tab.round(0).fillna(0).astype(int).to_string())


if __name__ == "__main__":
    main()

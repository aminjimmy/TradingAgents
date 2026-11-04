#!/usr/bin/env python3
"""Training session 2: self-retraining bot with a wider, reasoned menu.

All rule sets: RSI(2) H1 mean reversion, EMA200 side, daily trend + dollar filter (EURUSD proxy), $10 stop,
$30 target, 0.01 lot, real raw-account costs. Menu dimensions (each has a reason to help):
  RSI level      < 10 | < 15
  entry          market | limit 0.2 ATR better | limit 0.4 ATR better (valid 60 min)
  exit EMA       3 | 5 | 7
  hours          24h | skip the 23:00-01:00 server rollover (real spreads spike there)
Each January 2022..2026 the bot scores every rule set on earlier years only (t-statistic of per-trade R,
>= 100 trades) and trades the next year with the winner. Compared with the fixed v1.15 preset.

usage: python3 claude_bot_v2.py xau_m1.pkl
"""
import itertools
import os
import sys
from multiprocessing import Pool

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gold_scalper_bt import Params, run  # noqa: E402
from claude_bot import grow, tstat  # noqa: E402
from real_spread_test import costs, ea  # noqa: E402

YEARS = list(range(2020, 2027))
TEST_YEARS = [2022, 2023, 2024, 2025, 2026]
MENU = list(itertools.product([10, 15], [0.0, 0.2, 0.4], [3, 5, 7], ["24h", "no-rollover"]))
PRESET = (10, 0.0, 5, "24h")
M1 = {}


def rule_params(lo, lim, xema, hours, **extra):
    p = dict(ea("v1.10"), **costs("raw"))
    p.update(max_daily_loss_pct=0, fixed_lots=0.01, sl_atr=0.0, min_sl=10.0, rr=3.0,
             limit_offset_atr=lim, limit_valid_min=60,
             use_session=(hours != "24h"), sess_start=1, sess_end=23,
             sargs=dict(lo=lo, exit_ema=xema, filters=["daily_trend", "macro_eur20"]))
    p.update(extra)
    return Params(**p)


def label(rule):
    lo, lim, xema, hours = rule
    return f"RSI<{lo} {'market' if lim == 0 else f'limit{lim}ATR':10s} EMA{xema} {hours}"


def job(rule):
    tr, _, _ = run(M1["d"], rule_params(*rule), 1e6, quiet=True)
    df = pd.DataFrame(tr)[["open_t", "close_t", "r", "pnl"]]
    df["year"] = pd.to_datetime(df.open_t * 60, unit="s").dt.year
    return rule, df


def main():
    M1["d"] = pd.read_pickle(sys.argv[1])
    with Pool(4) as pool:
        trades = dict(pool.map(job, MENU))
    print(f"{'rule set':38s} " + " ".join(f"{y:>6d}" for y in YEARS) + f" {'trades':>6s} {'avgR':>6s} {'t20-23':>6s}")
    for rule in sorted(MENU, key=lambda r: -tstat(trades[r].r[trades[r].year < 2024])):
        df = trades[rule]
        by = df.groupby("year").r.sum().reindex(YEARS, fill_value=0)
        print(f"{label(rule):38s} " + " ".join(f"{v:+6.1f}" for v in by) +
              f" {len(df):6d} {df.r.mean():+6.3f} {tstat(df.r[df.year < 2024]):6.2f}{'  <- v1.15 preset' if rule == PRESET else ''}")

    print("\nYearly retraining (earlier years only):")
    chosen = []
    for Y in TEST_YEARS:
        scores = {r: tstat(trades[r].r[trades[r].year < Y]) for r in MENU if (trades[r].year < Y).sum() >= 100}
        best = max(scores, key=scores.get)
        live = trades[best][trades[best].year == Y]
        chosen.append(live)
        print(f"  {Y}: [{label(best)}] train t {scores[best]:.2f} -> {len(live)} trades {live.r.sum():+.1f}R "
              f"(preset that year: {trades[PRESET].r[trades[PRESET].year == Y].sum():+.1f}R)")
    bot = pd.concat(chosen).sort_values("close_t")
    ref = trades[PRESET][trades[PRESET].year >= 2022].sort_values("close_t")
    for nm, d in (("self-trained v2", bot), ("fixed v1.15 preset", ref)):
        pf = d.pnl[d.pnl > 0].sum() / -d.pnl[d.pnl < 0].sum()
        b3, dd3, _ = grow(d.r.to_numpy(), 100, 3)
        b5, dd5, _ = grow(d.r.to_numpy(), 100, 5)
        print(f"{nm:20s}: {len(d)} trades, avg {d.r.mean():+.3f}R, PF {pf:.2f}, total {d.r.sum():+.1f}R | "
              f"$100 @3%: ${b3:,.0f} (DD {dd3 * 100:.0f}%) | @5%: ${b5:,.0f} (DD {dd5 * 100:.0f}%)")


if __name__ == "__main__":
    main()

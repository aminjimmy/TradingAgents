#!/usr/bin/env python3
"""Claude's gold bot: a self-retraining version of everything the research supported.

Menu (12 rule sets, all RSI(2) mean reversion on H1, EMA5 exit, 24h, real raw-account costs):
  entry level  RSI(2) < 5 / 10 / 15 (mirror for shorts), EMA200 side
  stop/target  fixed $10 stop + $30 target   |   2 x ATR stop + 3R target
  filters      daily trend   |   daily trend + dollar trend (EURUSD proxy)

Training: at the start of each year 2022..2026 the bot scores every rule set on ALL EARLIER years only
(t-statistic of its per-trade R, needs >= 100 trades) and trades the next year with the winner.
Sizing: % of balance risked per trade, compounding, 0.001-lot steps (R-based, so it fits either stop type).

usage: python3 claude_bot.py xau_m1.pkl
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
from real_spread_test import costs, ea  # noqa: E402

YEARS = list(range(2020, 2027))
TEST_YEARS = [2022, 2023, 2024, 2025, 2026]
MENU = list(itertools.product([5, 10, 15], ["fixed$10", "atr2x"], ["daily", "daily+usd"]))
M1 = {}


def rule_params(lo, stop, flt):
    p = dict(ea("v1.10"), **costs("raw"))
    p.update(use_session=False, max_daily_loss_pct=0, fixed_lots=0.01,
             sargs=dict(lo=lo, filters=["daily_trend"] + (["macro_eur20"] if flt == "daily+usd" else [])))
    if stop == "fixed$10":
        p.update(sl_atr=0.0, min_sl=10.0, rr=3.0)
    else:
        p.update(sl_atr=2.0, min_sl=1.0, rr=3.0)
    return Params(**p)


def job(rule):
    tr, _, _ = run(M1["d"], rule_params(*rule), 1e6, quiet=True)
    df = pd.DataFrame(tr)[["open_t", "close_t", "r", "pnl", "dir"]]
    df["year"] = pd.to_datetime(df.open_t * 60, unit="s").dt.year
    return rule, df


def tstat(r):
    return r.mean() / r.std(ddof=1) * np.sqrt(len(r)) if len(r) > 1 else -np.inf


def grow(r_seq, start, risk_pct, floor=20.0):
    bal, peak, worst, path = start, start, 0.0, []
    for r in r_seq:
        bal = max(0.0, bal * (1 + risk_pct / 100 * r))
        peak = max(peak, bal); worst = max(worst, 1 - bal / peak if peak else 1)
        path.append(bal)
        if bal < floor:
            break
    return bal, worst, path


def name(rule):
    lo, stop, flt = rule
    return f"RSI<{lo}, {stop}, {flt}"


def main():
    M1["d"] = pd.read_pickle(sys.argv[1])
    with Pool(4) as pool:
        trades = dict(pool.map(job, MENU))

    print("Menu results by year (sum of R per year; 1R = the amount risked per trade):")
    print(f"{'rule set':34s} " + " ".join(f"{y:>6d}" for y in YEARS) + f" {'trades':>7s} {'avgR':>6s}")
    for rule in MENU:
        df = trades[rule]
        by = df.groupby("year").r.sum().reindex(YEARS, fill_value=0)
        print(f"{name(rule):34s} " + " ".join(f"{v:+6.1f}" for v in by) + f" {len(df):7d} {df.r.mean():+6.3f}")

    print("\nYearly retraining (choice made with earlier years only):")
    chosen = []
    for Y in TEST_YEARS:
        scores = {rule: tstat(trades[rule].r[trades[rule].year < Y]) for rule in MENU
                  if (trades[rule].year < Y).sum() >= 100}
        best = max(scores, key=scores.get)
        live = trades[best][trades[best].year == Y]
        chosen.append(live)
        print(f"  {Y}: picks [{name(best)}] (train t-stat {scores[best]:.2f}) -> traded {len(live)} trades, "
              f"{live.r.sum():+.1f}R, avg {live.r.mean():+.3f}R, win {(live.pnl > 0).mean() * 100:.0f}%")
    bot = pd.concat(chosen).sort_values("close_t")

    ref = trades[(10, "fixed$10", "daily+usd")]
    ref = ref[ref.year >= TEST_YEARS[0]].sort_values("close_t")
    print(f"\nSelf-trained bot 2022-2026: {len(bot)} trades ({len(bot) / 4.82:.0f}/yr), avg {bot.r.mean():+.3f}R, "
          f"PF {bot.pnl[bot.pnl > 0].sum() / -bot.pnl[bot.pnl < 0].sum():.2f}, total {bot.r.sum():+.1f}R")
    print(f"Hindsight-picked v1.15 preset, same years: {len(ref)} trades, avg {ref.r.mean():+.3f}R, total {ref.r.sum():+.1f}R")

    print("\n$100 account, compounding, 2022 -> Oct 2026 (actual order of trades):")
    print(f"{'risk':>5s} | {'self-trained bot':>34s} | {'hindsight v1.15 preset':>34s}")
    for risk in (3, 5, 10):
        b1, d1, p1 = grow(bot.r.to_numpy(), 100, risk)
        b2, d2, p2 = grow(ref.r.to_numpy(), 100, risk)
        yb = pd.Series(p1, index=pd.to_datetime(bot.close_t.to_numpy()[:len(p1)] * 60, unit="s")).groupby(lambda t: t.year).last()
        print(f"{risk:4d}% | ${b1:>9,.0f}  (max DD {d1 * 100:3.0f}%)            | ${b2:>9,.0f}  (max DD {d2 * 100:3.0f}%)")
        print(f"       year-end balances (self-trained): " + ", ".join(f"{y} ${v:,.0f}" for y, v in yb.items()))

    # resampled futures from the self-trained bot's live trades (by month)
    bot["month"] = pd.to_datetime(bot.close_t * 60, unit="s").dt.to_period("M")
    months = [bot.r[bot.month == m].to_numpy() for m in pd.period_range(bot.month.min(), bot.month.max(), freq="M")
              if str(m) != "2025-08"]
    rng = np.random.default_rng(11)
    print("\nFuture scenarios from the self-trained bot's live trades ($100 start, 3,000 paths):")
    print(f"{'risk':>5s} {'yrs':>3s} | {'typical':>8s} {'bad 10%':>8s} {'good 90%':>9s} | {'P(down)':>7s} {'P(<$50)':>7s} | {'med worst DD':>12s}")
    for risk in (3, 5):
        for yrs in (1, 3, 5):
            fins, dds = [], []
            for _ in range(3000):
                seq = np.concatenate([months[i] for i in rng.integers(0, len(months), 12 * yrs)])
                b, d, _ = grow(seq, 100, risk)
                fins.append(b); dds.append(d)
            fins = np.array(fins)
            print(f"{risk:4d}% {yrs:3d} | {np.median(fins):8,.0f} {np.percentile(fins, 10):8,.0f} {np.percentile(fins, 90):9,.0f} | "
                  f"{(fins < 100).mean() * 100:6.0f}% {(fins < 50).mean() * 100:6.0f}% | {np.median(dds) * 100:11.0f}%")


if __name__ == "__main__":
    main()

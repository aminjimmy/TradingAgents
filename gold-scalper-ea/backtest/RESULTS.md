# GoldScalperEA v1.00: Python backtest results

**Verdict: no edge. The EA as written should not be traded on a live account or on a demo.** Before costs, the signals break even. After a normal OANDA spread, it loses steadily on every timeframe, in every session and in 6 of 7 years.

## Setup
- **Data:** 1-minute XAUUSD bars, 2 Jan 2020 – 28 Oct 2026, 2.3M bars ([parshant65-lang/Gold-XAUUSD-1m-2020-2025-Historical-Data](https://github.com/parshant65-lang/Gold-XAUUSD-1m-2020-2025-Historical-Data)). Aug 2025 is missing.
  Times are converted to OANDA server time (New York + 7h).
- **Engine:** `gold_scalper_bt.py`, a bar-by-bar copy of the EA's rules, using MT5's indicator formulas.
- **Costs:** spread $0.30 and slippage $0.05 per side. Contract size 100 oz. Leverage 1:20. The news filter is off, as it is in the MT5 tester.
- **Fills:** orders fill at the next M1 open. If SL and TP are both touched inside one minute, SL is assumed.
- **Split:** the EA's default settings were not fitted to this data. Even so, the variant tests below were run on 2020–2023 only, and 2024–2026 was kept as the untouched check.

## Headline (default inputs, 1% risk, compounding)
| Period | Start | Trades | Win % | PF | Avg R | Net | Max DD |
|---|---|---|---|---|---|---|---|
| 2020–2023 (in-sample) | $10,000 | 2,775* | 42% | 0.72 | −0.19 | −99.0% | 99.1% |
| 2024–2026 (out-of-sample) | $10,000 | 4,278* | 48% | 0.80 | −0.07 | −94.5% | 94.6% |
| 2024–2026, your size | $100 (0.001 lot step) | 1,759* | 47% | 0.79 | −0.09 | −74.4% | 75.6% |
| 2024–2026, spread $0.15 | $10,000 | 6,206 | 51% | 0.94 | −0.02 | −80.6% | 84.3% |
| 2024–2026, spread $0.45 | $10,000 | 2,886 | 45% | 0.72 | −0.13 | −96.5% | 96.5% |

\* Trades stopped once the shrinking balance could no longer afford the minimum lot. This happened 16,649 times in-sample, 5,286 times out-of-sample, and 11,430 times in the $100 run.

Monte Carlo (2,000 reshuffles of the out-of-sample trades): **100% chance of ending below the starting balance.**

## Why it fails
- **No predictive power:** with zero spread and zero slippage, the in-sample average is **−0.004R per trade** (PF 0.97). Costs then turn break-even into a loss.
- **Costs are large relative to the stops:** the median M5 stop is only about $2.44, so the $0.40 round-trip cost is about 16% of the risk on every trade. M5 produced 57% of all trades and lost the most.
- **More confluence makes it worse:** min score 6 gives −0.19R and score 7 gives −0.24R. By the time all seven momentum indicators agree, the move has already happened.

## Variants tried (2020–2023, fixed 0.10 lot, no daily limits). None is profitable.
| Variant | Trades | Avg R | PF |
|---|---|---|---|
| Default | 11,409 | −0.176 | 0.74 |
| Default, zero cost | 11,273 | −0.004 | 0.97 |
| H1 only | 808 | −0.085 | 0.84 |
| M30 + H1 | 2,296 | −0.103 | 0.80 |
| SL 2.5×ATR | 8,194 | −0.102 | 0.82 |
| R:R 2, no break-even/trailing | 9,576 | −0.172 | 0.79 |
| R:R 3 with trailing | 10,295 | −0.184 | 0.74 |
| No trend filter | 26,250 | −0.184 | 0.74 |
| H1 trend filter | 12,343 | −0.172 | 0.74 |
| ADX ≥ 25 | 8,057 | −0.177 | 0.74 |
| London/NY hours only | 8,042 | −0.199 | 0.71 |
| Min score 6 / 7 | 7,155 / 1,585 | −0.190 / −0.240 | 0.72 / 0.68 |

The safety machinery itself works as designed: break-even, trailing, time exit, Friday close, daily loss stop and the minimum-lot refusal all behave correctly. The problem is the entry logic.

## Reproduce
```
python3 prepare_data.py <data_root> xau_m1.pkl
python3 gold_scalper_bt.py xau_m1.pkl --start 10000 --from 2024-01-01 --out trades.csv
```
`trades.csv` uses the same columns as the `bt_analyze.py` script from the XAU backtest skill.

*This is a historical simulation, not financial advice.*

---

# v1.10: replacement entry engines

**Method:** I tested three different kinds of entry, each with management suited to it, and compared each with **random entries using the same exits**. That comparison stops a gold bull run, rather than the signal, from making a strategy look good. All design choices were made on 2020–2023. The candidate (`rsi2_H1`) was fixed in advance and then run **once** on 2024–2026. Sizes were fixed (results in R) and costs were $0.30 spread plus $0.05 slippage. Code: `strategies.py` and `strategy_search.py`.

## Design period 2020–2023
| Engine | Trades | Avg R | PF | Random baseline with same exits |
|---|---|---|---|---|
| London opening-range breakout (M15) | 744 | −0.207 | 0.69 | −0.150. Worse than random. |
| NY opening-range breakout (M15) | 700 | −0.165 | 0.80 | −0.150 |
| Donchian 20 trend breakout (H1) | 611 | −0.070 | 0.85 | −0.095. About the same as random. |
| **RSI(2) mean reversion (H1)** | 818 | **−0.012** | 0.96 | **−0.122. Clearly better than random.** |
| RSI(2) (H1), zero cost | 813 | +0.043 | 1.12 | |

RSI(2) on M15 (−0.07) and M30 (−0.05) was worse than on H1, because costs take a bigger share of their smaller stops. The refinements I tried (stop 3 × ATR, exit EMA 3 or 10, level 5 or 20, H4 trend filter) all landed between −0.025 and −0.009. That is a flat plateau, which is a sign of robustness, not curve-fitting.

## Unseen period 2024–2026 (run once)
| Engine | Trades | Avg R | PF | Notes |
|---|---|---|---|---|
| **RSI(2) H1** | 478 | **+0.013** | **1.08** | Before costs +0.047R, which **matches the design period (+0.043R)**. Random entries with the same exits: −0.034. |
| Donchian 20 (H1) | 353 | +0.076 | 1.16 | Not an edge: random **long** entries scored +0.115, and Donchian lost money in 2020–2023. |
| London opening-range breakout | 400 | −0.030 | 0.98 | |

## RSI(2) H1 sensitivity to spread (avg R / PF)
| Spread | 2020–2023 | 2024–2026 |
|---|---|---|
| $0.10 | +0.017 / 1.04 | +0.028 / 1.11 |
| $0.20 | +0.001 / 0.99 | +0.018 / 1.10 |
| $0.30 | −0.012 / 0.96 | +0.013 / 1.08 |
| $0.40 | −0.026 / 0.92 | +0.006 / 1.07 |

## Full EA simulation (0.5% risk, all risk limits on, compounding)
| Run | Trades | Return | PF | Max DD |
|---|---|---|---|---|
| 2020–2023, $10k | 818 | −4.9% | 0.95 | 10.7% |
| 2024–2026, $10k | 435 | +1.2% | 1.03 | 7.3% |
| 2024–2026, $100 (0.001 lot step) | 10 | +1.1% | n/a | 1.0% (807 trades refused: the minimum lot is too big for H1 stops) |

**Verdict:** v1.10 replaces a strategy that wiped out the account with one that roughly breaks even and has a small edge confirmed on unseen data. It still does **not** pass the PF ≥ 1.1 bar after realistic costs, so it should only run on demo. The spread you pay matters more than any indicator setting. On a $100 account it can barely trade.

---

# Real-spread test (instead of an MT5 real-tick run)

**What was possible:** MT5's "real ticks" mode downloads ticks from the broker's server, and this environment can't run MT5 or reach any tick-data host. Dukascopy, Exness, OANDA, TrueFX and Kaggle are all blocked by the network policy, and GitHub has no raw gold ticks for 2020–2026.
Instead, I used **real spread statistics measured from 176M Exness XAUUSD bid/ask ticks (Jan 2024–Jul 2026)**, taken from [datxbt/xauusd-research-ORB](https://github.com/datxbt/xauusd-research-ORB) (`spread_stats/`).
They're copied to `spread_data/`. They give the average spread for every UTC minute of the day, for each year. That means the backtest now pays the real spread pattern, including the 2–3× widening at the 22:00 UTC rollover, instead of a flat number.

**Limits:** these are *average* spreads per minute of day, not the spread on each individual day, so news spikes are smoothed out. The 2020–2023 runs use the 2024 profile. Price paths are still 1-minute bars. On H1 with stops of $15 or more, the order of fills inside a minute hardly matters.

**Cost models** (`real_spread_test.py`):
- **raw**: the real Exness raw-spread average for that minute (mean $0.061 over 2024–26), plus a $7/lot round-turn commission.
- **standard**: the same real intraday shape, scaled to a $0.30 average, with no commission. This is like a typical standard account.
- **fixed30**: the earlier flat $0.30.

| EA | Costs | Period | Trades | Avg R | PF | $10k return | Max DD |
|---|---|---|---|---|---|---|---|
| v1.10 | **raw** | 2020–23 | 814 | **+0.013** | 1.03 | **+4.7%** | 6.8% |
| v1.10 | **raw** | 2024–26 | 477 | **+0.026** | 1.11 | **+5.5%** | 6.8% |
| v1.10 | standard | 2020–23 | 817 | −0.009 | 0.97 | −3.7% | 10.1% |
| v1.10 | standard | 2024–26 | 478 | +0.014 | 1.08 | +1.9% | 7.2% |
| v1.00 | raw | 2020–23 | 11,263 | −0.092 | 0.84 | −98.9% | 99.2% |
| v1.00 | raw | 2024–26 | 7,065 | −0.005 | 0.98 | −67.5% | 77.2% |
| v1.00 | standard | 2024–26 | 7,011 | −0.041 | 0.94 | −91.4% | 92.2% |

**Full 2020–2026 run, v1.10, raw costs, one $10k account:** 1,268 trades, **+9.5%** over almost 7 years, PF 1.06, max DD 8.2%, win rate 65%, worst losing streak 8.
Monte Carlo (3,000 reshuffles with 0–10% cost/exit stress): median max DD 15.2%, 95th percentile DD 28.8%, **72% chance of ending below the start**.

**Verdict:**
- On a low-cost (raw-spread + commission) account, v1.10 is **slightly profitable in both the design period and the unseen period**.
- That's the first time any version has passed both. But the edge is **too thin to survive small extra costs**, as the Monte Carlo shows. It roughly breaks even on a standard-spread account.
- v1.00 loses under every cost model.
- What decides the result is the type of trading account, not the indicators. It's suitable for demo forward-testing on a raw/ECN-type account. It isn't ready for live money.

---

# Round 3: profit-maximisation attempts, outside ideas, trust checks (v1.11)

All runs use **real raw-account costs** (the Exness tick spread profile plus $7/lot commission).

## Ideas from GitHub research
I read `n30dyn4m1c/gold-pro-scalper` (an MT5 gold mean-reversion EA built around costs) and took its testable ideas:
- a cost gate
- a limit take-profit at the mean
- turn confirmation
- an ATR regime band
- an ADX cap
- break-even

I rejected its "dynamic risk tiers" (10% risk per trade on small accounts) as a ruin setting.
I added `backtesting.py` (kernc, PyPI) as an independent second engine.

## One-change-at-a-time refinements (`refine_search.py`)
**Rule, fixed before running:** keep a change only if total R per year rises in **both** halves **and** PF does not fall in either half.

| Change | 2020–23 R/yr (PF) | 2024–26 R/yr (PF) | Kept? |
|---|---|---|---|
| **baseline v1.10** | **+2.7 (1.03)** | **+4.4 (1.11)** | — |
| add M30 | −3.6 (0.99) | −9.3 (1.04) | no |
| add M15 + M30 | −19.3 (0.96) | −31.6 (1.02) | no |
| add H4 | −1.0 (0.91) | +2.6 (0.93) | no |
| SL 1.5 / 3 / 4 × ATR | −1.4 / −0.1 / −0.3 | +5.3 / +3.3 / +3.9 | no (helps in only one half) |
| exit when RSI(2) > 70 | +2.0 (1.01) | +5.5 (1.14) | no |
| limit TP at EMA5 (GitHub idea) | −2.0 (0.95) | −5.2 (0.89) | no: it cuts winners |
| turn confirmation (GitHub idea) | −2.1 (0.94) | +6.5 (1.07) | no |
| ADX ≤ 25 / ≤ 30 (GitHub idea) | +2.0 / −0.9 | +1.1 / +2.6 | no |
| ATR band 0.5–2.0 (GitHub idea) | +3.8 (1.06) | +4.2 (1.10) | no (slightly worse in 2024–26) |
| cost gate 4× (GitHub idea) | +2.6 (1.03) | +4.4 (1.11) | no (almost never binds on H1) |
| RSI level 5 / 15 | −3.1 / +0.6 | −1.5 / +2.2 | no |
| break-even at 1 ATR | +1.3 (1.01) | +4.0 (1.09) | no |
| 2 positions per TF | −1.5 (0.96) | +8.1 (1.16) | no |
| **24h trading (no session filter)** | **+3.8 (1.04)** | **+7.5 (1.08)** | **near miss:** more profit in both halves, but PF fell 1.11 → 1.08. Available as an opt-in. |
| session 09–20 | +1.4 (1.00) | +3.7 (1.11) | no |

**Result: nothing passed.** The v1.10 rules already sit on a plateau that these ideas can't lift without curve-fitting.

## Permutation test (`permutation_test.py`, 200 random runs per period)
The random runs used entries on the **same trend side** (long above EMA200, short below), the same exits, the same sessions, real costs and a matched trade count.

| Period | v1.10 avg R | Random mean / 95th pct / max | p-value |
|---|---|---|---|
| 2020–2026 | +0.016 | −0.008 / +0.011 / +0.034 | **0.03** |
| 2020–2023 | +0.013 | −0.016 / +0.014 / +0.031 | 0.06 |
| 2024–2026 | +0.026 | +0.008 / +0.049 / +0.066 | 0.22 |

The RSI(2) timing beats random timing over the full sample, but the evidence is modest and isn't significant in 2024–26 on its own.
Most of the result comes from the structure: trade with the EMA200 side and exit quickly at EMA5.

## Independent engine cross-check (`crosscheck_backtestingpy.py`)
Same rules, H1 bars, flat $0.13/oz round-trip cost:

| Period | backtesting.py | Our engine |
|---|---|---|
| 2020–23 | 813 trades, avg R +0.027, PF 1.05, win 65% | 814 trades, avg R +0.026, PF 1.07, win 65% |
| 2024–26 | 477 trades, avg R +0.038, PF 1.12, win 67% | 477 trades, avg R +0.031, PF 1.12, win 66% |

The two engines agree, so the results are not an artefact of our simulator.

## Risk per trade: the only real "more profit" lever (`risk_sizing.py`, 2020–2026, $10k, raw costs, all limits on)
| Risk | Return | Per year | PF | Max DD | MC median DD | MC 95% DD | P(DD > 20%) |
|---|---|---|---|---|---|---|---|
| **0.5% (default)** | +9.5% | +1.3% | 1.06 | 8.2% | 14.9% | 26.0% | 22% |
| 1.0% | +17.6% | +2.4% | 1.05 | 16.4% | 30.7% | 49.1% | 86% |
| 1.5% | +32.1% | +4.2% | 1.06 | 26.2% | 41.6% | 63.6% | 98% |
| 2.0% | +58.7% | +7.0% | 1.08 | 31.5% | 48.8% | 72.1% | 100% |
| 3.0% | +105.8% | +11.2% | 1.09 | 45.3% | 61.3% | 84.1% | 100% |
| 1.0%, 24h | +31.1% | +4.0% | 1.07 | 15.1% | 31.0% | 49.6% | 88% |

Monte Carlo: 3,000 compounding reshuffles with 0–10% adverse stress per trade. The stress alone is enough to remove most of this thin edge (P(end below start) is about 70% at every risk level).

## Final verdict (v1.11)
- **Strategy:** unchanged from v1.10, because nothing beat it under fair rules. It's a small, real-but-weak edge. On a raw/ECN-cost account it makes about +1.3%/yr at 0.5% risk, with a max drawdown of about 8%. It roughly breaks even on a standard-spread account.
- **Profit can only be raised with risk, and drawdown rises with it.** Recommendation: 0.5–1% risk at most. Above 1.5%, the simulations say a deep drawdown is close to certain at some point.
- **Added in v1.11:** a trade-log CSV, so MT5 real-tick tests and demo trading can be compared with these simulations using the same analysis script.

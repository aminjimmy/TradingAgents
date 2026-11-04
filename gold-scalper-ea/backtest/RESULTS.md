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

---

# Requested check: "lo 0.01", 24h, 1% (2020–2026, raw costs)

| Case | Trades | Return | PF | Max DD | Notes |
|---|---|---|---|---|---|
| 24h, 1% risk, $10k (reference) | 1,784 | +31.1% | 1.07 | 15.1% | 2020–23 +12.1%, 2024–26 +20.5%; MC 95% DD 49.6% |
| RSI(2) level `lo` = 0.01, 24h, 1% | 0 | — | — | — | RSI(2) < 0.01 happened on only 4 of 38,447 H1 bars, and none of them passed the trend filter |
| Fixed 0.01 lot, 24h, $10k | 1,791 | +4.1% | 1.06 | 7.0% | Same trades, smaller size |
| Fixed 0.01 lot, 24h, $100, 1:20 leverage | 10 | −19.3% | 0.31 | 22.7% | After that, margin for 0.01 lot exceeded a $100 account (3,220 trades refused) |
| Fixed 0.01 lot, 24h, $100, 1:100 | 1,705 | **−66% ($33.97 left)** | — | 96% | Average loss $10.44 (10% of the account per losing trade) |
| Fixed 0.01 lot, 24h, $100, 1:500, 2024–26 | 143 | **−100% (account wiped out 19 Jul 2024)** | — | 100% | |
| 1% risk, 24h, $100 (0.01 minimum lot) | 0 | — | — | — | The 0.01 minimum lot never fits a 1% risk on H1 stops |

Largest single loss: 30 Jan 2026. Gold was at about $5,225, with H1 ATR about $109, so a normal 2×ATR stop was $218 per ounce (−$218 on 0.01 lot). The price data is genuine, not a glitch.
**Change in the EA:** `InpFixedLotMaxRiskPct` (default 3%) now skips a fixed-lot trade whenever its stop would risk more than that share of equity.

---

# Requested check: 0.01 lot at the recommended 0.5% risk (24h, raw costs, 1:100, 2020–2026)

**A) 0.5% risk sizing, with 0.01 as the minimum lot and lot step (the recommended setup):**

| Start | Trades | Skipped (0.01 too big) | 2020–26 | Per yr | PF | Max DD | 2020–23 | 2024–26 | MC 95% DD |
|---|---|---|---|---|---|---|---|---|---|
| $100 | 0 | 3,243 | — | — | — | — | — | — | — |
| $1,000 | 59 | 3,138 | −3.0% | −0.4% | 0.72 | 6.3% | −5.1% | +2.6% | 9.2% |
| $2,500 | 1,160 | 1,172 | +6.2% | +0.9% | 1.05 | 6.6% | +7.9% | +3.0% | 22.0% |
| $5,000 | 1,504 | 552 | +7.8% | +1.1% | 1.05 | 6.3% | +6.4% | +4.1% | 26.7% |
| **$10,000** | 1,744 | 96 | **+15.6%** | **+2.1%** | 1.08 | 7.5% | +6.9% | +10.8% | 26.7% |
| $25,000 | 1,786 | 11 | +16.3% | +2.2% | 1.08 | 7.9% | +7.2% | +10.3% | 29.1% |

**B) Fixed 0.01 lot, with a trade skipped whenever its stop would risk more than 0.5% (`InpFixedLots=0.01`, `InpFixedLotMaxRiskPct=0.5`):**
$100: 0 trades. $1k: −3.9%. $2.5k: +4.4%. $5k: +1.6%. $10k: +9.5% (PF 1.17, max DD 2.2%). $25k: +2.1%. A fixed lot doesn't grow with the account, so returns shrink as a percentage on larger balances. The good $10k figure comes from which high-volatility trades the cap happened to skip at that balance, so it's not a robust result.

**Takeaway:** at 0.5% risk, a 0.01-lot gold contract needs about **$5,000–10,000** before the EA can take most of its H1 trades. Below about $2,500 it either can't trade, or it only takes the quiet-market trades, which lose.

---

# Requested check: fixed 0.01 lot, $10 stop, $15–30 target (2020–2026, raw costs, 1:100)

0.01 lot = 1 oz, so $10 per trade = a $10 price move. The daily % loss limit was off, because 4% of a small account is less than one $10 loss.
"+EMA5 exit" = the v1.11 rule that closes a trade early when price crosses back over EMA5. "SL/TP only" = no early exit.

| Setup | Trades | Win % | Avg win | Avg loss | PF | Net | Per yr | 2020–23 | 2024–26 | Max DD | Max losing run |
|---|---|---|---|---|---|---|---|---|---|---|---|
| SL $10 / TP $15, +EMA5 exit, 24h | 1,979 | 60% | $5.89 | −$8.08 | 1.08 | +$496 | +$73 | +$205 | +$291 | $148 | 7 |
| SL $10 / TP $20, +EMA5 exit, 24h | 1,975 | 59% | $6.23 | −$8.11 | 1.10 | +$665 | +$97 | +$246 | +$418 | $179 | 7 |
| SL $10 / TP $25, +EMA5 exit, 24h | 1,972 | 59% | $6.38 | −$8.11 | 1.12 | +$778 | +$114 | +$234 | +$544 | $167 | 10 |
| **SL $10 / TP $30, +EMA5 exit, 24h** | 1,971 | 59% | $6.47 | −$8.12 | 1.12 | **+$826** | **+$121** | +$245 | +$581 | $198 | 10 |
| SL $10 / TP $15–30, SL/TP only, 24h | 1,599–1,711 | 37–45% | $12–17 | −$9.35 | 1.05–1.07 | +$441 to +$666 | | −$160 to +$94 | +$444 to +$660 | $228–481 | 14–15 |
| SL $10 / TP $15–30, +EMA5 exit, 09–23 | 1,384–1,386 | 59–61% | | | 1.08–1.13 | +$357 to +$613 | | +$141 to +$176 | +$216 to +$437 | $190–224 | 8–11 |

- Only 2–10% of trades reach the take-profit. Most close earlier at EMA5, so the target level matters much less than the stop.
- TP $30 / EMA5 / 24h by year: 2020 +$101, 2021 +$43, 2022 +$59, 2023 +$43, **2024 −$39**, 2025 +$265, 2026 +$354.

**As real accounts (TP $30, EMA5 exit, 24h):** started in 2020: $100 → $926 (lowest point $75), $500 → $1,326, $1,000 → $1,826.
**Started in Jan 2024: $100 → $24 (−76%)**, after which there wasn't enough margin to keep trading. $500 → $1,116 (max DD 26%).

**Monte Carlo** (one year ≈ 290 trades, reshuffled 2,000 times with up to 10% extra cost/slippage stress), chance of being knocked out below about $60 (where margin for 0.01 lot runs out):
$100: **≈76%**. $250: ≈18%. $500: ≈0.2%. $1,000: 0%. Under the stress, the median result after a year is roughly break-even.

**Caveats:** this picks the best of 16 combinations, which flatters the result a little. A fixed $10 stop also gets tighter as gold's price and volatility rise (H1 ATR in 2026 is often above $20), and that is why 2024 lost. EA v1.12 adds `InpFixedSLPrice` / `InpFixedTPPrice` to run this setup.

---

# Multiple indicators as extra filters (`indicator_search.py`)

**Setup:** RSI(2) H1, 0.01 lot, $10 stop, $30 target, EMA5 exit, 24h, raw costs, 2020–2026. Each indicator was added on its own as an extra entry confirmation.
**Rule (fixed beforehand):** profit higher than the baseline in both halves and in at least 5 of 7 years.

| Indicator filter | Trades | Win % | PF | Net | Max DD | 2020–23 | 2024–26 | Years better |
|---|---|---|---|---|---|---|---|---|
| **baseline** | 1,971 | 58.5 | 1.12 | +$826 | $198 | +$245 | +$581 | — |
| Stochastic 5,3,3 extreme | 947 | 59.3 | 1.19 | +$587 | $179 | +$68 | +$519 | 1/7 |
| Bollinger band touch | 797 | 53.8 | 0.99 | −$30 | $327 | −$173 | +$143 | 0/7 |
| Williams %R extreme | 703 | 57.9 | 1.19 | +$478 | $192 | +$127 | +$351 | 1/7 |
| CCI ±100 | 929 | 54.5 | 1.01 | +$43 | $225 | −$61 | +$104 | 0/7 |
| MACD histogram turn | 86 | 70.9 | 1.58 | +$104 | $30 | +$47 | +$56 | 1/7 |
| ADX ≤ 25 (range) | 790 | 58.7 | 1.05 | +$128 | $214 | +$163 | −$35 | 3/7 |
| ADX ≥ 25 (trend) | 1,329 | 58.5 | 1.14 | +$640 | $172 | +$33 | +$607 | 2/7 |
| **Daily trend (D1 close vs EMA50)** | 1,530 | 59.9 | **1.20** | **+$989** | **$173** | +$242 | **+$746** | 4/7 |
| ≥1 ATR from EMA20 | 903 | 54.6 | 1.04 | +$132 | $251 | −$15 | +$148 | 1/7 |
| Rejection wick | 691 | 58.6 | 0.96 | −$97 | $237 | −$2 | −$95 | 2/7 |
| RSI(14) < 40 / > 60 | 632 | 55.1 | 1.06 | +$158 | $184 | +$47 | +$111 | 0/7 |
| Two closes against | 1,796 | 59.1 | 1.12 | +$718 | $218 | +$210 | +$508 | 3/7 |
| Ichimoku cloud side | 1,121 | 61.3 | 1.22 | +$749 | $160 | +$227 | +$521 | 3/7 |
| ATR regime 0.5–2× | 1,956 | 58.6 | 1.12 | +$795 | $202 | +$265 | +$530 | 2/7 |
| London/NY hours | 1,172 | 58.4 | 1.14 | +$555 | $200 | +$117 | +$438 | 2/7 |
| H4 EMA50/200 trend | 1,328 | 58.7 | 1.19 | +$835 | $181 | +$159 | +$677 | 3/7 |

**No indicator passed the strict rule.** Filters with a high PF (Stochastic, Williams %R, Ichimoku, MACD) remove good trades along with bad ones, so total profit falls.

**Quality per trade, measured in each half separately** (a second look, so treat it as weaker evidence):

| Filter | PF 2020–23 / 2024–26 | $ per trade | Net 2020–23 / 2024–26 |
|---|---|---|---|
| baseline | 1.10 / 1.15 | $0.23 / $0.70 | +$245 / +$616 |
| **daily trend** | **1.12 / 1.26** | **$0.28 / $1.16** | **+$242 / +$753** |
| ichimoku | 1.18 / 1.24 | $0.36 / $1.08 | +$227 / +$519 |
| daily trend + ichimoku | 1.11 / 1.35 | $0.23 / $1.46 | +$113 / +$501 |
| daily trend + H4 | 1.09 / 1.25 | $0.22 / $1.16 | +$159 / +$684 |

**Conclusion:** the D1 trend filter improves quality in both halves without costing profit, and it lowers drawdown. It fails the strict profit rule only by $3 in 2020–23 and by beating the baseline in 4 of 7 years rather than 5. Stacking more indicators doesn't help.
EA v1.13 adds it as an option (`InpUseDailyTrend`, default off). It's worth testing on demo with the $10/$30 setup.

---

# Daily / weekly / monthly profile (`period_report.py`)

**Setup:** RSI(2) H1 + **daily trend filter on**, **0.01 lot**, $10 stop, $30 target, EMA5 exit, 24h, raw costs, 2020 to 28 Oct 2026. Aug 2025 is excluded because there's no data for it.
"Win days" counts only days with a closed trade (the bot traded on 54% of weekdays). Weeks and months include periods with no trades.

| Variant | Trades | Net | 2020–23 | 2024–26 | Max DD | Win days | Win weeks | Win months | Avg/day | Avg/week | Avg/month | Worst day | Worst week | Worst month |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **no daily target/stop** | 1,530 | **+$989** | +$242 | +$746 | $173 | 64% | 48% | 54% | +$1.02 | +$2.83 | +$12.21 | −$40 | −$64 | −$54 |
| stop trading at +$10/day | 1,479 | +$944 | +$237 | +$707 | $145 | 65% | 48% | 54% | +$0.98 | +$2.71 | +$11.66 | −$40 | −$64 | −$54 |
| stop trading at +$20/day | 1,516 | +$870 | +$226 | +$644 | $163 | 64% | 48% | 54% | +$0.90 | +$2.49 | +$10.74 | −$40 | −$64 | −$54 |
| stop trading at +$30/day | 1,528 | +$972 | +$242 | +$729 | $173 | 64% | 48% | 54% | +$1.00 | +$2.78 | +$11.99 | −$40 | −$64 | −$54 |
| daily stop −$20 | 1,459 | +$909 | +$305 | +$604 | $243 | 63% | 48% | 54% | +$0.94 | +$2.60 | +$11.22 | −$23 | −$51 | −$84 |
| +$20 target and −$20 stop | 1,444 | +$778 | +$289 | +$490 | $263 | 63% | 48% | 54% | +$0.81 | +$2.23 | +$9.61 | −$23 | −$51 | −$114 |

**Daily profit targets and daily $ stops don't help.** Every version earns less, and the −$20 stop makes the worst month deeper. This happens because winning days are small and frequent, while the profit comes from a few big days that a target cuts short.

**Base setup by year:** 2020 +$105, 2021 −$7, 2022 +$43, 2023 +$101, 2024 +$41, 2025 +$200, 2026 +$505.
Best day +$60, best week +$139, best month +$244 (Sep 2026). Median trading day +$1.89, median month +$3.08.

**Monthly P&L ($, 0.01 lot):**

| Year | Jan | Feb | Mar | Apr | May | Jun | Jul | Aug | Sep | Oct | Nov | Dec |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2020 | −4 | 6 | 66 | 22 | −14 | 27 | 49 | 0 | −8 | −25 | 2 | −16 |
| 2021 | 9 | 6 | −36 | −17 | 46 | 36 | 10 | −46 | −16 | −21 | 5 | 17 |
| 2022 | −4 | −5 | −20 | −9 | 25 | −9 | 21 | 10 | −38 | 95 | −4 | −20 |
| 2023 | 35 | 14 | −19 | −22 | 47 | 5 | 9 | 33 | −6 | −6 | 0 | 11 |
| 2024 | −40 | 46 | −8 | 4 | −7 | −54 | −19 | 70 | 58 | 1 | −26 | 16 |
| 2025 | −16 | 88 | 4 | 3 | 4 | −5 | 0 | n/a | 63 | 77 | −8 | −9 |
| 2026 | 30 | −41 | 55 | −30 | 16 | 37 | −36 | 59 | 244 | 171 | — | — |

**Caveat:** Sep–Oct 2026 alone made +$415, which is 42% of the total. Without those two months, the average is about $7 a month.

---

# 1 / 3 / 5 / 10-year scenarios (`projection.py`)

**Method:** these are scenarios, not predictions. Futures are built by resampling the 81 real months of 2020–2026 trades, 4,000 paths per row, with real raw-account costs.
**Setup:** RSI(2) H1 + daily trend, $10 stop, $30 target, EMA5 exit, 24h.
**Modes:** **fixed** = always 0.01 lot. **compounding** = 0.01 lot per $500 of balance.
A path counts as **knocked out** if the balance drops below $60, where 0.01-lot margin runs out.

**Start $500, all months (avg $12.21/month at 0.01 lot)**

| Years | Fixed: bad / typical / good | Compounding: bad / typical / good | P(below start) fixed / compounding |
|---|---|---|---|
| 1 | $466 / $631 / $855 | $468 / $624 / $845 | 16% / 17% |
| 3 | $605 / $919 / $1,286 | $608 / $916 / $1,489 | 3% / 4% |
| 5 | $808 / $1,222 / $1,689 | $795 / $1,322 / $2,778 | 1% / 1% |
| 10 | $1,344 / $1,934 / $2,596 | $1,465 / **$4,003** / $13,929 | 0% / 0% |

Bad = 10th percentile, typical = median, good = 90th percentile. Median worst drawdown along the way: 17–22% (fixed), 17–30% (compounding).

**Start $500, cautious (Sep–Oct 2026 removed, avg $7.26/month)**

| Years | Fixed: bad / typical / good | Compounding: bad / typical / good | P(below start) |
|---|---|---|---|
| 1 | $449 / $582 / $735 | $450 / $586 / $734 | 21–23% |
| 3 | $512 / $758 / $1,011 | $518 / $760 / $984 | 8–9% |
| 5 | $624 / $930 / $1,253 | $624 / $916 / $1,398 | 3% |
| 10 | $928 / $1,371 / $1,815 | $885 / **$1,485** / $3,099 | 1% |

**Start $100 (either mode):** about **57% of paths are knocked out**, usually in the first year. Typical outcome: about $59, and stuck there. Good outcome after 10 years: $2,000–4,400.

**Actual 2020–2026 history, compounding from $500, year-end balances:** 2020 $605, 2021 $599, 2022 $642, 2023 $742, 2024 $783, 2025 $950, 2026 $1,916.

**Assumptions:** the future behaves like 2020–2026, nothing is withdrawn, spreads stay at raw-account levels, no swap costs on holds, and execution matches the simulation. Any worse cost or a change in how gold behaves lowers every number.

---

# Lot size growing with profit (`lot_growth.py`)

**Rule:** start at $500 with 0.01 lot and **add 0.01 lot for every $X of profit above $500**. If profit is given back, the lot shrinks again.
The setup and resampled real months are the same as `projection.py` (3,000 paths per row). Bad / typical / good = 10th / 50th / 90th percentile. "Med DD" is the typical worst drawdown along the path.

**All months (future like 2020–2026):**

| Lot growth | 1 yr typical | 3 yr typical | 5 yr typical | 10 yr bad / typical / good | 10 yr med DD / 95% DD | Typical max lot at 10 yr |
|---|---|---|---|---|---|---|
| fixed 0.01 | $630 | $923 | $1,213 | $1,344 / $1,948 / $2,607 | 22% / 43% | 0.01 |
| +0.01 per $500 | $630 | $911 | $1,304 | $1,425 / **$3,962** / $12,926 | 30% / 46% | 0.08 |
| +0.01 per $250 | $624 | $952 | $1,778 | $1,657 / **$13,196** / $152,420 | 50% / 68% | 0.67 |
| +0.01 per $100 | $585 | $961 | $2,292 | $911 / $35,444 / $8.8M | 87% / 98% | 10.8 |
| +0.01 per $50 | $540 | $614 | $684 | $482 / **$784** / $255,815 | 98% / 100% | 7.5 |

**Cautious (Sep–Oct 2026 removed):**

| Lot growth | 1 yr typical | 3 yr typical | 5 yr typical | 10 yr bad / typical / good | 10 yr med DD |
|---|---|---|---|---|---|
| fixed 0.01 | $587 | $754 | $933 | $938 / $1,370 / $1,826 | 26% |
| +0.01 per $500 | $586 | $756 | $915 | $891 / **$1,505** / $3,158 | 30% |
| +0.01 per $250 | $582 | $715 | $913 | $736 / **$1,843** / $8,334 | 46% |
| +0.01 per $100 | $559 | $626 | $703 | $531 / $1,005 / $15,800 | 75% |
| +0.01 per $50 | $524 | $529 | $532 | $438 / **$531** / $1,025 | 81% |

**Actual 2020–2026 replay from $500, year-end balances:**
- fixed: $605, $599, $642, $742, $783, $983, **$1,489**
- per $500: …, $950, **$1,916** (max lot 0.03)
- per $250: …, $735, $1,085, **$3,320** (max lot 0.13)
- per $100: $591, $562, $602, $702, $682, $1,129, **$4,813** (max lot 0.53)
- per $50: $521, $505, $524, $586, $536, $522, **$21,328** (max lot 6.38, built almost entirely in Sep–Oct 2026)

**Reading it:** growing lots faster raises the lucky outcomes enormously, but it also makes drawdowns much deeper. Too fast (per $50–100) usually **ends up worse than fixed lots**: a drawdown hits while the lot is large, the account falls back to 0.01 lot, and it can't recover the loss.
**+0.01 per $250–500 is the sensible range.** EA v1.14 adds `InpLotGrowthStepUSD` and `InpGrowthStartBalance` to run this.

---

# Training the bot to read the chart (machine learning, `ml_train.py`)

**Method:**
- **Examples:** every RSI(2) pullback setup on H1 in 2020–2026.
- **Labels:** win or loss under the user's exact rules (0.01 lot, $10 SL, $30 TP, EMA5 exit, 24h, raw costs).
- **Features:** about 45 chart readings at the signal bar (`ml_features.py`): RSI on H1/H4/D1, distance to EMA5/20/50/200 in ATRs, EMA slopes, volatility versus normal, ADX/DI, Bollinger position and width, Stochastic, MACD, returns over 1–72 h, candle shape, losing/winning streaks, position in the 24h range, distance to yesterday's high and low, daily and H4 trend, the $10 stop measured in ATRs, hour of day and day of week.
- **Models:** LightGBM (gradient-boosted trees) and logistic regression.
- **Testing:** walk-forward. Each test year 2022–2026 is predicted by a model trained only on earlier years, with a purge so no training trade overlaps the test year. The model keeps the top 50% of setups, and the picked trades run through the normal EA rules.

**Round 1** (with a raw-dollar ATR feature): AUC 0.54–0.55. The models rejected almost everything in 2025–26 because gold's dollar volatility had doubled (they kept 29 of 625 setups in 2026).
Logistic picks: 741 trades, 67% win, PF 1.23, **+$362**, max DD $86. The current plan made **+$916**.

**Round 2** (price-level-free features, adaptive cut-off; this is a second attempt, so it's weaker evidence):

| Unseen 2022–2026 | Trades | Win % | PF | Net | Max DD | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|---|---|---|
| **current plan (RSI2<10 + daily trend)** | 1,107 | 58.1 | 1.24 | **+$916** | $173 | +58 | +101 | +41 | +190 | +527 |
| wide pool, all setups (RSI2<15) | 2,022 | 55.2 | 1.06 | +$488 | $270 | +56 | +32 | +106 | +76 | +218 |
| wide pool, LightGBM picks 50% | 1,030 | 58.5 | 1.04 | +$124 | $285 | +120 | +68 | −41 | +25 | −48 |
| wide pool, logistic picks 50% | 1,028 | 58.9 | 1.07 | +$222 | $389 | +98 | +54 | +141 | +144 | −215 |
| wide pool, random 50% (avg of 20) | 1,252 | 57.0 | 1.08 | +$363 | $306 | | | | | |
| plan's setups, LightGBM picks 50% | 552 | 62.0 | 1.22 | +$377 | $280 | +48 | +62 | +78 | −10 | +199 |
| **plan's setups, logistic picks 50%** | 563 | **65.0** | **1.43** | +$657 | $137 | +56 | +9 | +140 | +107 | +346 |
| plan's setups, random 50% (avg of 20; best +$789) | 680 | 60.1 | 1.26 | +$573 | $133 | +33 | +75 | +69 | +119 | +277 |

**What the models leaned on most:** daily trend strength (which the plan already uses), the 24h range in ATRs, Bollinger width, EMA200 slope, daily RSI, H4 trend, volatility versus normal, and distance to yesterday's high and low.

**Verdict:** with chart and indicator data alone, the models predict trade outcomes only slightly better than a coin flip (AUC about 0.55).
Used as an extra filter, the logistic model raises the win rate (58% → 65%) and PF (1.24 → 1.43), but it halves the number of trades. It earns less in total than the current plan and isn't clearly better than keeping a random half.
**The hand-built plan stays the best choice, and the EA is unchanged.**
Real improvement would need information the chart doesn't contain, such as the US dollar index, US real yields, the economic calendar, or real tick and order-flow data. None of these can be downloaded in this environment.

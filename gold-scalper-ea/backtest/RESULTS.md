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

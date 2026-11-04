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

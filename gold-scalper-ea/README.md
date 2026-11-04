# GoldScalperEA v1.11: XAUUSD EA for OANDA MT5

An Expert Advisor (EA) for MetaTrader 5 that trades gold (XAUUSD). It has two entry engines, and both use the same set of risk limits:

| Engine | `InpEntryMode` | Status after the 2020–2026 backtest |
|---|---|---|
| **RSI(2) mean reversion on H1** | `ENTRY_MEAN_REVERSION` (default) | The only engine with a real edge. That edge held up on unseen 2024–2026 data, but it is **thin: about break-even after costs** (PF 1.03–1.08). |
| Indicator confluence, M5–H1 (v1.00) | `ENTRY_CONFLUENCE` | **Lost about 95% in both periods.** It is kept only for reference. |

> **Warning:** v1.10 is a demo-only candidate, not a proven money-maker. Its result depends on the spread: at a $0.30 spread
> it roughly breaks even, while at $0.10–0.20 it is slightly positive. See [`backtest/RESULTS.md`](backtest/RESULTS.md).
> The backtest data did not support an aggressive M5/M15 scalper, because costs wipe out the edge on small stops.

## How v1.11 decides to trade (defaults, same rules as v1.10)

On every closed **H1** bar:
- **Buy** when the close is **above EMA200** and **RSI(2) < 10**: a short, sharp dip inside an uptrend.
- **Sell** when the close is **below EMA200** and **RSI(2) > 90**.
- **Exit** when the close crosses back over **EMA5**. Otherwise the trade closes at the SL (2 × ATR), at the TP (6 × ATR, rarely reached), or after 24 bars.

M5, M15 and M30 can still be switched on (`InpUseM5` and so on), but in testing the lower timeframes did worse after costs.

## Risk and trade management

- **Risk** is 0.5% of equity per trade. The SL is 2 × ATR (at least $1.00). Break-even and trailing stops are off, because they hurt this engine.
- If even the broker's minimum lot would risk more than the risk %, the trade is **refused**. On a $100 account, this blocks almost every H1 trade.
- **Daily loss limit** of 4%: the EA closes its positions and stops until the next day. Other limits: max 30 trades/day, max 4 positions, and a 60-minute cooldown after 4 losses in a row.
- **Filters**: spread ≤ $0.50, session hours 09–23 server time, flat by Friday 21:00, no new trades from 30 min before to 30 min after high-impact USD news (live only).

## Installation (Windows PC)

1. Download **OANDA MetaTrader 5** from your OANDA account (Tools → MT5) and log in. Use a **demo** account first.
2. In MT5: **File → Open Data Folder**, then go to `MQL5\Experts\`.
3. Copy `MQL5/Experts/GoldScalperEA.mq5` from this repo into that folder.
4. Open **MetaEditor** (press F4 in MT5), open the file, and press **Compile** (F7). It should report `0 errors`.
   If you get errors, paste them to Claude and they will be fixed.
5. In MT5, enable **Algo Trading** (toolbar button) and turn on **Tools → Options → Expert Advisors → Allow algorithmic trading**.
6. Open an XAUUSD chart. The timeframe doesn't matter, because the EA reads M5/M15/M30/H1 internally. Then drag **GoldScalperEA** from the Navigator onto the chart.
7. A status panel in the top-left of the chart shows day P/L, open positions, the trend, and each timeframe's latest score.

OANDA may name the symbol `XAUUSD`, `XAUUSD.pro`, `XAUUSD.sml` or similar. Attach the EA to whichever gold symbol your account offers.
Set the session hours using **OANDA's server time**. You can see the server time in Market Watch.

## Backtesting (do this before going live)

Strategy Tester (Ctrl+R):
- Expert: `GoldScalperEA`, Symbol: your XAUUSD, Period: M5
- Modelling: **Every tick based on real ticks**
- Date range: at least 12 months. Tune on the first 8–9 months and check the last 3–4 months untouched (out-of-sample).
- Deposit: your real intended size. Leverage: your account's.

In MT5, check that the result is close to the Python backtest: about 160 trades a year on H1, profit factor around 1.0–1.1.
If the real-tick result is clearly worse, your account's spread is too high for this strategy.
Don't optimize many inputs at once, because that overfits. If you do tune anything, keep `InpMR_Level` between 5 and 20.

## Choosing risk and options

| Setting | Recommendation | Why |
|---|---|---|
| Account type | **Raw / ECN-style pricing with commission** if OANDA offers it for gold | With real raw costs it makes about +1.3%/yr at 0.5% risk. On a $0.30-spread account it roughly breaks even. |
| `InpRiskPercent` | **0.5** (default), at most **1.0** | At 2–3% the history shows +59–106%, but the Monte Carlo puts the 95% worst-case drawdown at 72–84%. |
| `InpUseSession=false` (trade 24h) | Optional | +31% vs +18% over 2020–26 at 1% risk, but it fell just short of the acceptance rule and adds rollover-hour trades where real spreads spike. Keep `InpMaxSpreadPrice` on. |
| M5 / M15 / M30 / H4 | Keep off | They lost money with every cost model, including raw spreads. |

## Trade log (v1.11)

With `InpLogTrades=true`, the EA appends every open and close to `Terminal\Common\Files\GoldScalper_<symbol>_<magic>_trades.csv`.
Strategy Tester runs get a `TEST_` prefix. The columns match the `bt_analyze.py` script from the XAU backtest skill, so real-tick or demo results can be compared directly with `backtest/RESULTS.md`.

## Settings for the legacy v1.00 confluence engine

To reproduce v1.00, set `InpEntryMode=ENTRY_CONFLUENCE`, turn all four timeframes on, set `InpUseTrendFilter=true`, `InpRiskPercent=1.0`,
`InpSLAtrMult=1.5`, `InpRewardRisk=1.5`, `InpBreakEvenR=0.8`, `InpTrailStartR=1.0`, `InpCloseOnOpposite=true`.

## Backtest status

The full results and method are in [`backtest/RESULTS.md`](backtest/RESULTS.md) (three rounds, plus a permutation test and an independent `backtesting.py` cross-check). Short version: the v1.00 confluence engine lost about 95%. RSI(2) H1, the v1.10 default, made
−4.9% in 2020–2023 and +1.2% in 2024–2026 (max drawdown about 11%) at a $0.30 spread. It is a real but small edge, so test it on demo before trusting it.

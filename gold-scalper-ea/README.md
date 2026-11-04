# GoldScalperEA: XAUUSD multi-timeframe scalper for OANDA MT5

An Expert Advisor (EA) for MetaTrader 5 that scalps gold (XAUUSD) on **M5, M15, M30 and H1** at the same time.
Each timeframe trades on its own, with its own magic number, and all of them share one set of risk limits.

> **Warning:** Aggressive scalping of gold is high risk. This EA has **not been backtested or run live yet**.
> Before you put real money in, compile it, backtest it with "Every tick based on real ticks", and run it on an
> **OANDA demo account for at least 2–4 weeks**.

## How it decides to trade

On every closed bar of each enabled timeframe, the EA:

1. **Higher-timeframe trend filter** (default H4): only buys when price and EMA50 are above EMA200, and only sells in the opposite case.
2. **Confluence score (0–7)** for each direction:
   | # | Check (long side; short side is the mirror) |
   |---|---|
   | 1 | EMA9 above EMA21 |
   | 2 | RSI between 50 and 70 and rising |
   | 3 | MACD histogram positive and growing |
   | 4 | ADX ≥ 20 and +DI above −DI |
   | 5 | Close in the upper half of the Bollinger Bands but still inside them |
   | 6 | Stochastic %K above %D and not overbought |
   | 7 | Bullish candle with a decisive body (≥35% of its range) |
3. **Entry trigger**: at least one of these must be true: a pullback that bounces off EMA9, a fresh EMA9/21 cross, or a Stochastic cross up from below 50.
4. It enters when the score is ≥ `InpMinScore` (default 5), there is a trigger, ADX is strong enough, and all filters pass.

## Risk and trade management

- **SL** = ATR × 1.5 (at least $1.00). **TP** = SL × 1.5.
- **Lot size** comes from `InpRiskPercent` of equity (default 1% per trade). If the margin needed is more than free margin, the lot size is scaled down.
- **Break-even** at +0.8R (locks in $0.10). **ATR trailing stop** starts from +1R.
- **Time exit**: a trade is closed after 24 bars of its own timeframe.
- **Opposite signal**: a new opposite signal on the same timeframe closes that timeframe's position.
- **Daily loss limit** of 4%: when reached, the EA closes all its positions and stops trading until the next server day.
- **Max 30 trades/day**, **max 4 positions open at once**, and a **60-minute cooldown after 4 losses in a row**.
- **Filters**: spread ≤ $0.50, session hours 09–23 server time, flat by Friday 21:00, no new trades from 30 min before to 30 min after high-impact USD news. The news filter works live only, because the MT5 calendar is not available in the Strategy Tester.

Worst case: when all 4 timeframes signal together, the total risk is about 4 × `InpRiskPercent`.
To lower this, reduce `InpMaxTotalPos` or the risk %.

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

Good inputs to optimize: `InpMinScore` (4–6), `InpSLAtrMult` (1.0–2.5), `InpRewardRisk` (1.0–2.5), `InpAdxMin` (15–30),
`InpTrendTF` (H1/H4), and which timeframes are enabled. Don't optimize many inputs at once: that overfits.

## Presets

| Setting | Aggressive (default) | Moderate |
|---|---|---|
| InpRiskPercent | 1.0 | 0.5 |
| InpMinScore | 5 | 6 |
| InpMaxTotalPos | 4 | 2 |
| InpMaxDailyLossPct | 4.0 | 2.5 |
| InpUseM5 | true | false |
| InpMaxTradesPerDay | 30 | 12 |

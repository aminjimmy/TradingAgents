# Live forward test on an OANDA practice account

`oanda_bot.py` is a Python copy of the v1.15 preset (the setup Claude's self-retraining bot picked).
- **Rules:** RSI(2) H1 pullbacks on XAU_USD, daily trend + dollar filter (EUR_USD), $10 stop / $30 target, EMA5 exit, 24h time limit, flat by Friday 21:00 server time, 5% risk per trade.
- **Schedule:** it runs **once per hour** as a scheduled cloud task.
- **No state of its own:** OANDA holds every position and the trade history (trades are tagged `claude-gold`), so each run is independent and safe to repeat.
- **Practice accounts only:** it refuses to trade a live account.

**Parity:** `parity_test.py` replays 14,203 H1 bars (2024-01 → 2026-09). The live signal function gives **100% identical** signals to the backtester.

## Setup (once)
1. Create an OANDA **practice** (fxTrade Practice / v20) account. Generate an API token under **Manage API Access**.
2. In the cloud environment settings (environment menu → Edit):
   - **Network access → Allowed domains:** `api-fxpractice.oanda.com`
   - **Environment variables:** `OANDA_API_TOKEN` = your token, `OANDA_ACCOUNT_ID` = e.g. `101-001-1234567-001`
3. Optional: `RISK_PCT` (default 5).

## Use
```
python3 live/oanda_bot.py --dry-run   # show the decision without trading
python3 live/oanda_bot.py             # one live decision cycle (the hourly task runs this)
python3 live/report.py                # results so far, incl. "what $100 at 5% would be now"
```

**Sizing:** practice accounts trade gold in the instrument's unit precision. On a large practice balance the bot risks 5% of NAV per trade, and `report.py` converts each trade into R to show the equivalent $100 / 5% account.

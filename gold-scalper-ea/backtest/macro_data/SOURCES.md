# Macro data sources

All series are daily. They were taken from public GitHub mirrors of FRED and Yahoo Finance, because direct access to those sites was blocked in the build environment. The data was downloaded on 2026-11-04.

| File | Series | Mirror | Coverage | Cross-check |
|---|---|---|---|---|
| DFII10.csv | FRED 10-year TIPS real yield | achl0902-web/back-testing | 2003 – 2026-11-02 | identical to el0617/SIG_FALL_26 copy (2020+) |
| DGS10.csv, DGS2.csv | FRED 10y / 2y Treasury yields | achl0902-web/back-testing | – 2026-11-02 | DGS10 identical to jwavalosq/Analytics-on-Finance (2020+) |
| DTWEXBGS.csv | FRED broad trade-weighted dollar | achl0902-web/back-testing | 2006 – 2026-10-30 | identical to el0617/SIG_FALL_26 (2020+) |
| T10YIE.csv | FRED 10y breakeven inflation | achl0902-web/back-testing | – 2026-11-03 | |
| Y_DXY.csv | Yahoo ICE dollar index | achl0902-web/back-testing | 1980 – 2026-11-03 | matches evan7646-cloud ICE DXY (median diff 0.004) |
| Y_TNX.csv, VIXCLS.csv, Y_OIL.csv, Y_SPX.csv | 10y yield, VIX, oil, S&P 500 | achl0902-web/back-testing | – Nov 2026 | |
| FOMC_DATES.csv | Fed meeting dates | achl0902-web/back-testing | 1994 – 2026-09-16 | |
| DEXUSEU.csv | FRED EURUSD | jzh3/Lieberman-Warner-Actual-vs-Prediction | 2007 – 2026-09-25 | 20-day moves agree with DXY 93% of the time (corr 0.96) |

Gold cross-check: Yahoo gold matches the 1-minute XAUUSD backtest data within about 1% every quarter, 2020–2026.

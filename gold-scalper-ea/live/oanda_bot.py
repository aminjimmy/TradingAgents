#!/usr/bin/env python3
"""Claude's gold bot - live forward test on an OANDA v20 PRACTICE account. Run once per hour.

Rules (identical to the backtested v1.15 preset / claude_bot.py choice):
  - H1 XAU_USD (mid prices). Signal on the last COMPLETED H1 candle.
  - Long:  close > EMA200 and RSI(2) < 10;  short: close < EMA200 and RSI(2) > 90.
  - Daily trend: previous completed NY-close day's close vs D1 EMA50 must agree with the direction.
  - Dollar filter: EUR_USD 20-day change (completed NY-close days) > 0 for longs, < 0 for shorts.
  - Stop $10, target $30 (server-side), exit when an H1 close crosses back over EMA5,
    close after 24 hours, flat by Friday 21:00 broker-server time (= 14:00 New York).
  - One position at a time; max spread $0.50; cooldown 60 min after 4 losses in a row (same server day).
  - Size: RISK_PCT % of account NAV / $10 stop, in the instrument's unit precision.
State lives in OANDA (trades are tagged), so every run is independent and safe to repeat.

Environment:  OANDA_API_TOKEN, OANDA_ACCOUNT_ID   (practice account)
Optional:     OANDA_ENV=practice (default) | live (refused unless OANDA_ALLOW_LIVE=yes)
              RISK_PCT=5  STOP_USD=10  TARGET_USD=30
usage:  python3 oanda_bot.py            # one decision cycle, places orders
        python3 oanda_bot.py --dry-run  # same, but only prints what it would do
"""
import json
import math
import os
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests

INSTRUMENT = "XAU_USD"
DOLLAR_PROXY = "EUR_USD"
TAG = "claude-gold"
NY = ZoneInfo("America/New_York")

RSI_N, RSI_LO, TREND_EMA, EXIT_EMA = 2, 10.0, 200, 5
D1_EMA, USD_DAYS = 50, 20
MAX_BARS_H, MAX_SPREAD = 24, 0.50
MAX_CONSEC_LOSSES, COOLDOWN_MIN = 4, 60
FRIDAY_CLOSE_SERVER_HOUR = 21


# ------------------------------------------------------------------ indicators (same formulas as the backtester)
def ema(x, n):
    return x.ewm(span=n, adjust=False).mean()


def rsi(c, n):
    d = c.diff()
    ag = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    al = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + ag / al.replace(0, np.nan))


def server_time(ts_utc):
    """Broker-server clock used by the backtests: New York time + 7h."""
    return ts_utc.astimezone(NY).replace(tzinfo=None) + timedelta(hours=7)


def decide_entry(h1_close, d1_close, eur_d1_close):
    """Pure signal function (also used by the parity test).
    h1_close: completed H1 closes (last = signal bar); d1_close / eur_d1_close: completed daily closes.
    Returns (direction, info dict)."""
    r = rsi(h1_close, RSI_N).iloc[-1]
    tr = ema(h1_close, TREND_EMA).iloc[-1]
    c = h1_close.iloc[-1]
    d = 1 if (c > tr and r < RSI_LO) else (-1 if (c < tr and r > 100 - RSI_LO) else 0)
    d1_up = d1_close.iloc[-1] > ema(d1_close, D1_EMA).iloc[-1]
    usd_chg = eur_d1_close.iloc[-1] / eur_d1_close.iloc[-1 - USD_DAYS] - 1     # EUR up = dollar down
    info = dict(close=round(float(c), 3), rsi2=round(float(r), 2), ema200=round(float(tr), 3),
                daily_trend="up" if d1_up else "down", eurusd_chg20_pct=round(float(usd_chg) * 100, 3))
    if d == 0:
        info["why"] = "no RSI(2) setup"
        return 0, info
    if (d > 0) != d1_up:
        info["why"] = "against daily trend"
        return 0, info
    if (d > 0 and usd_chg <= 0) or (d < 0 and usd_chg >= 0):
        info["why"] = "dollar filter not supportive"
        return 0, info
    info["why"] = "signal"
    return d, info


def exit_signal(h1_close, side):
    x = ema(h1_close, EXIT_EMA).iloc[-1]
    c = h1_close.iloc[-1]
    return (side > 0 and c > x) or (side < 0 and c < x)


# ------------------------------------------------------------------ OANDA v20 REST
class Oanda:
    def __init__(self):
        env = os.environ.get("OANDA_ENV", "practice")
        if env != "practice" and os.environ.get("OANDA_ALLOW_LIVE") != "yes":
            sys.exit("Refusing to run against a live account (set OANDA_ENV=practice).")
        self.base = "https://api-fxpractice.oanda.com/v3" if env == "practice" else "https://api-fxtrade.oanda.com/v3"
        token, self.acct = os.environ.get("OANDA_API_TOKEN"), os.environ.get("OANDA_ACCOUNT_ID")
        if not token or not self.acct:
            sys.exit("Set OANDA_API_TOKEN and OANDA_ACCOUNT_ID in the environment settings.")
        self.s = requests.Session()
        self.s.headers.update({"Authorization": f"Bearer {token}", "Content-Type": "application/json"})

    def get(self, path, **params):
        r = self.s.get(self.base + path, params=params, timeout=30)
        r.raise_for_status()
        return r.json()

    def send(self, method, path, body):
        r = self.s.request(method, self.base + path, data=json.dumps(body), timeout=30)
        if r.status_code >= 400:
            raise RuntimeError(f"{method} {path} -> {r.status_code}: {r.text[:400]}")
        return r.json()

    def candles(self, instrument, granularity, count, **extra):
        js = self.get(f"/instruments/{instrument}/candles", granularity=granularity, count=count, price="M", **extra)
        rows = [(pd.Timestamp(c["time"]), float(c["mid"]["c"])) for c in js["candles"] if c["complete"]]
        s = pd.Series([v for _, v in rows], index=pd.DatetimeIndex([t for t, _ in rows]))
        return s

    def daily(self, instrument, count):
        return self.candles(instrument, "D", count, dailyAlignment=17, alignmentTimezone="America/New_York")


# ------------------------------------------------------------------ one decision cycle
def run_once(dry):
    api = Oanda()
    now_utc = datetime.now(timezone.utc)
    now_srv = server_time(now_utc)
    log = dict(run_utc=now_utc.isoformat(timespec="seconds"), server_time=str(now_srv)[:16], dry_run=dry, actions=[])

    acct = api.get(f"/accounts/{api.acct}/summary")["account"]
    nav = float(acct["NAV"])
    log["nav"] = nav
    inst = api.get(f"/accounts/{api.acct}/instruments", instruments=INSTRUMENT)["instruments"][0]
    unit_prec, min_units, disp = int(inst["tradeUnitsPrecision"]), float(inst["minimumTradeSize"]), int(inst["displayPrecision"])
    px = api.get(f"/accounts/{api.acct}/pricing", instruments=INSTRUMENT)["prices"][0]
    bid, ask = float(px["bids"][0]["price"]), float(px["asks"][0]["price"])
    log.update(bid=bid, ask=ask, spread=round(ask - bid, 3), tradeable=px.get("tradeable", True))

    h1 = api.candles(INSTRUMENT, "H1", 2500)
    d1 = api.daily(INSTRUMENT, 200)
    eur = api.daily(DOLLAR_PROXY, 60)
    bar_time = h1.index[-1]                       # OANDA stamps candles with their START time
    bar_end = bar_time + pd.Timedelta(hours=1)
    log["signal_bar_utc"] = bar_time.isoformat()

    open_trades = [t for t in api.get(f"/accounts/{api.acct}/openTrades")["trades"]
                   if t["instrument"] == INSTRUMENT and t.get("clientExtensions", {}).get("tag") == TAG]

    def close_trade(t, why):
        log["actions"].append(dict(close=t["id"], why=why, units=t["currentUnits"], unrealized=t.get("unrealizedPL")))
        if not dry:
            api.send("PUT", f"/accounts/{api.acct}/trades/{t['id']}/close", {"units": "ALL"})

    # ---- manage open trades
    friday_close = now_srv.weekday() == 4 and now_srv.hour >= FRIDAY_CLOSE_SERVER_HOUR
    for t in list(open_trades):
        side = 1 if float(t["currentUnits"]) > 0 else -1
        opened = pd.Timestamp(t["openTime"])
        if friday_close:
            close_trade(t, "friday close"); open_trades.remove(t); continue
        if now_utc - opened.to_pydatetime() >= timedelta(hours=MAX_BARS_H):
            close_trade(t, "24h time exit"); open_trades.remove(t); continue
        if bar_end > opened and exit_signal(h1, side):     # a full H1 bar has closed since entry
            close_trade(t, "EMA5 exit"); open_trades.remove(t); continue

    # ---- entry
    direction, info = decide_entry(h1, d1, eur)
    log["signal"] = info
    reason = None
    if direction == 0:
        reason = info["why"]
    elif open_trades:
        reason = "already in a position"
    elif friday_close:
        reason = "Friday close window"
    elif not log["tradeable"]:
        reason = "market not tradeable"
    elif ask - bid > MAX_SPREAD:
        reason = f"spread {ask - bid:.2f} > {MAX_SPREAD}"
    elif now_utc - bar_end.to_pydatetime() > timedelta(minutes=55):
        reason = "signal bar is stale (run too late)"
    else:
        # idempotency + cooldown from recent closed trades
        closed = api.get(f"/accounts/{api.acct}/trades", state="CLOSED", instrument=INSTRUMENT, count=50)["trades"]
        ours = [t for t in closed if t.get("clientExtensions", {}).get("tag") == TAG]
        cid = f"cg-{bar_time.strftime('%Y%m%d%H')}"
        if any(t.get("clientExtensions", {}).get("id") == cid for t in ours):
            reason = "already traded this signal bar"
        else:
            day_start_srv = now_srv.replace(hour=0, minute=0, second=0, microsecond=0)
            today = sorted([t for t in ours if server_time(pd.Timestamp(t["closeTime"]).to_pydatetime()) >= day_start_srv],
                           key=lambda t: t["closeTime"])
            streak, last_loss = 0, None
            for t in today:
                if float(t["realizedPL"]) < 0:
                    streak += 1; last_loss = pd.Timestamp(t["closeTime"])
                elif float(t["realizedPL"]) > 0:
                    streak = 0
            if streak >= MAX_CONSEC_LOSSES and last_loss is not None and \
                    now_utc - last_loss.to_pydatetime() < timedelta(minutes=COOLDOWN_MIN):
                reason = f"cooldown after {streak} losses"
    if reason:
        log["entry"] = f"no trade: {reason}"
    else:
        risk_pct = float(os.environ.get("RISK_PCT", "5"))
        stop, target = float(os.environ.get("STOP_USD", "10")), float(os.environ.get("TARGET_USD", "30"))
        units = math.floor(nav * risk_pct / 100 / stop * 10 ** unit_prec) / 10 ** unit_prec
        if units < min_units:
            log["entry"] = f"no trade: size {units} below minimum {min_units} (NAV {nav:.2f} too small for {risk_pct}% risk)"
        else:
            entry_px = ask if direction > 0 else bid
            tp = round(entry_px + direction * target, disp)
            body = {"order": {
                "type": "MARKET", "instrument": INSTRUMENT, "units": f"{direction * units:.{unit_prec}f}",
                "timeInForce": "FOK", "positionFill": "DEFAULT",
                "stopLossOnFill": {"distance": f"{stop:.{disp}f}"},
                "takeProfitOnFill": {"price": f"{tp:.{disp}f}"},
                "tradeClientExtensions": {"tag": TAG, "id": f"cg-{bar_time.strftime('%Y%m%d%H')}",
                                          "comment": f"RSI2={info['rsi2']} risk={risk_pct}%"}}}
            log["entry"] = dict(side="BUY" if direction > 0 else "SELL", units=units, approx_price=entry_px,
                                stop_distance=stop, take_profit=tp)
            if not dry:
                res = api.send("POST", f"/accounts/{api.acct}/orders", body)
                fill = res.get("orderFillTransaction")
                log["entry"]["result"] = (f"filled @ {fill['price']} trade {fill.get('tradeOpened', {}).get('tradeID')}"
                                          if fill else f"not filled: {json.dumps(res)[:300]}")
    print(json.dumps(log, indent=1, default=str))
    return log


if __name__ == "__main__":
    run_once(dry="--dry-run" in sys.argv)

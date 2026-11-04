"""Alternative entry engines for gold_scalper_bt.py.

Each function takes resampled bars `b` (index = bar open time, server time), Params `p`
(strategy arguments in p.sargs) and the TF name, and returns a DataFrame aligned to `b` with:
  dir   1 / -1 / 0  signal evaluated at the close of that bar
  score informational (written to the trades log as "confidence")
  atr   ATR of that bar (used for stop distance and trailing)
  xl/xs optional: close longs / shorts of this TF at the close of that bar
"""
import numpy as np
import pandas as pd

from gold_scalper_bt import ema, rsi, true_range


def _atr(b, n=14):
    return true_range(b["high"], b["low"], b["close"]).rolling(n).mean()


def _out(b, d, atr, xl=None, xs=None):
    d = np.asarray(d, dtype=int).copy()
    d[:300] = 0
    df = pd.DataFrame({"dir": d, "score": np.abs(d) * 7, "atr": atr}, index=b.index)
    if xl is not None:
        df["xl"] = np.asarray(xl, dtype=bool)
        df["xs"] = np.asarray(xs, dtype=bool)
    return df


def sig_orb(b, p, name):
    """Session opening-range breakout: first close outside the range built between
    range_start and range_end (server hours), traded until window_end."""
    a = p.sargs
    rs, re_, we = a.get("range_start", 2.0), a.get("range_end", 10.0), a.get("window_end", 14.0)
    hr = b.index.hour + b.index.minute / 60.0
    day = b.index.normalize()
    inr = (hr >= rs) & (hr < re_)
    rhi = b["high"].where(inr).groupby(day).transform("max")
    rlo = b["low"].where(inr).groupby(day).transform("min")
    c, pc = b["close"], b["close"].shift(1)
    win = (hr >= re_) & (hr < we)
    up = win & (c > rhi) & (pc <= rhi)
    dn = win & (c < rlo) & (pc >= rlo)
    width = (rhi - rlo) / _atr(b)
    ok = (width >= a.get("min_width_atr", 0.0)) & (width <= a.get("max_width_atr", 1e9))
    d = pd.Series(np.where(up & ok, 1, np.where(dn & ok, -1, 0)), index=b.index)
    first = (d != 0).astype(int).groupby(day).cumsum() == 1      # one breakout per day
    d = d.where(first, 0)
    return _out(b, d, _atr(b))


def sig_rsi2(b, p, name):
    """Short-term mean reversion inside the trend: buy RSI(2) washouts above EMA200,
    sell RSI(2) spikes below it.

    sargs (all optional; defaults reproduce v1.10):
      lo=10, rsi_n=2, trend=200, exit_ema=5
      exit_mode   "ema" (close crosses exit EMA) | "rsi" (RSI(2) back above 70 / below 30)
      limit_exit  True -> also post a limit take-profit at the exit EMA, re-targeted each bar
      turn        True -> RSI extreme on the previous bar AND the signal bar closes back in our favour
      adx_max     only trade when ADX(14) <= this (ranging market)
      atr_band    (lo, hi): ATR / ATR-50-bar-average must sit inside this band
      cost, cost_k  distance from close to exit EMA must be >= cost_k x cost ($)
    """
    from gold_scalper_bt import adx_mt5
    a = p.sargs
    c = b["close"]
    lo = a.get("lo", 10.0)
    r = rsi(c, a.get("rsi_n", 2))
    tr = ema(c, a.get("trend", 200))
    x = ema(c, a.get("exit_ema", 5))
    atr = _atr(b)
    if a.get("turn"):
        long_ = (c > tr) & (r.shift(1) < lo) & (c > c.shift(1))
        short = (c < tr) & (r.shift(1) > 100 - lo) & (c < c.shift(1))
    else:
        long_ = (c > tr) & (r < lo)
        short = (c < tr) & (r > 100 - lo)
    ok = pd.Series(True, index=b.index)
    if a.get("adx_max"):
        adx, _, _ = adx_mt5(b["high"], b["low"], c, 14)
        ok &= adx <= a["adx_max"]
    if a.get("atr_band"):
        ratio = atr / atr.rolling(50).mean()
        ok &= (ratio >= a["atr_band"][0]) & (ratio <= a["atr_band"][1])
    if a.get("cost_k"):
        need = a["cost_k"] * a.get("cost", 0.15)
        long_ &= (x - c) >= need
        short &= (c - x) >= need
    d = np.where(long_ & ok, 1, np.where(short & ok, -1, 0))
    if a.get("exit_mode", "ema") == "rsi":
        xl, xs = r > 70, r < 30
    else:
        xl, xs = c > x, c < x
    if a.get("exit_mode") == "none":     # only SL / TP / time limit close trades
        xl = xs = None
    out = _out(b, d, atr, xl=xl, xs=xs)
    if a.get("limit_exit"):
        out["tgt"] = x
    return out


def sig_donchian(b, p, name):
    """Trend breakout: close beyond the prior N-bar high/low in the EMA200 direction,
    exit on the opposite N/2-bar channel (classic turtle-style)."""
    a = p.sargs
    n = a.get("n", 20)
    c = b["close"]
    tr = ema(c, a.get("trend", 200))
    hh = b["high"].rolling(n).max().shift(1)
    ll = b["low"].rolling(n).min().shift(1)
    m = max(2, n // 2)
    d = np.where((c > hh) & (c > tr), 1, np.where((c < ll) & (c < tr), -1, 0))
    xl = c < b["low"].rolling(m).min().shift(1)
    xs = c > b["high"].rolling(m).max().shift(1)
    return _out(b, d, _atr(b), xl=xl, xs=xs)


def sig_random(b, p, name):
    """Baseline: random entries (side +1, -1 or 0 = random both) at rate `prob` per bar.
    With p.use_trend=True this becomes 'random entries in the H4 trend direction'."""
    a = p.sargs
    rng = np.random.default_rng(a.get("seed", 1) * 1000 + len(b))
    hit = rng.random(len(b)) < a.get("prob", 0.03)
    side = a.get("side", 0)
    s = np.where(rng.random(len(b)) < 0.5, 1, -1) if side == 0 else np.full(len(b), side)
    if a.get("trend_side"):   # same direction rule as RSI(2): long above EMA, short below
        s = np.where(b["close"] > ema(b["close"], a["trend_side"]), 1, -1)
    xl = xs = None
    if a.get("mimic_exit_ema"):
        x = ema(b["close"], a["mimic_exit_ema"])
        xl, xs = b["close"] > x, b["close"] < x
    return _out(b, np.where(hit, s, 0), _atr(b), xl=xl, xs=xs)


STRATEGIES = {"orb": sig_orb, "rsi2": sig_rsi2, "donchian": sig_donchian, "random": sig_random}

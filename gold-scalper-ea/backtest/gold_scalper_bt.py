#!/usr/bin/env python3
"""Bar-by-bar Python replica of GoldScalperEA.mq5 for backtesting on 1-minute XAUUSD data.

Mirrors the EA: M5/M15/M30/H1 signal engines (7-point confluence + trigger), H4 EMA50/200
trend filter, ATR stops, risk-% sizing, break-even, ATR trailing, time exit, opposite-signal
exit, daily loss limit, trades/day cap, loss-streak cooldown, session hours, Friday close.
Indicators follow MetaTrader 5's built-in formulas (SMA-signal MACD, MT5 iADX, SMA ATR).

Execution model (on 1-minute bars, prices treated as BID):
  - signals are evaluated when a TF bar closes; orders fill at the next M1 open
  - BUY fills at ask = bid + spread (+ slippage); SELL fills at bid (- slippage)
  - SL/TP checked against each M1 high/low; if both are touched in one bar, SL is assumed
  - break-even / trailing are updated at each M1 open and close
  - the news filter is OFF (as in the MT5 Strategy Tester)

usage: python3 gold_scalper_bt.py data.pkl --start 10000 --spread 0.30 --out trades.csv
"""
import argparse
import csv
import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

TF_LIST = [("M5", 5), ("M15", 15), ("M30", 30), ("H1", 60), ("H4", 240)]


@dataclass
class Params:
    use_tf: dict = field(default_factory=lambda: {"M5": True, "M15": True, "M30": True, "H1": True})
    strategy: str = "confluence"   # see strategies.py
    sargs: dict = field(default_factory=dict)
    use_trend: bool = True
    trend_min: int = 240
    trend_fast: int = 50
    trend_slow: int = 200
    ema_fast: int = 9
    ema_slow: int = 21
    rsi_n: int = 14
    rsi_buy_max: float = 70
    rsi_sell_min: float = 30
    macd: tuple = (12, 26, 9)
    adx_n: int = 14
    adx_min: float = 20
    require_adx: bool = True
    bb_n: int = 20
    bb_dev: float = 2.0
    sto: tuple = (5, 3, 3)
    sto_ob: float = 80
    sto_os: float = 20
    atr_n: int = 14
    min_score: int = 5
    risk_pct: float = 1.0
    fixed_lots: float = 0.0
    fixed_lot_max_risk_pct: float = 0.0   # skip fixed-lot trades whose stop risks more than this % (0=off)
    max_lots: float = 5.0
    sl_atr: float = 1.5
    rr: float = 1.5
    min_sl: float = 1.0
    max_pos_tf: int = 1
    max_pos_total: int = 4
    max_daily_loss_pct: float = 4.0
    limit_offset_atr: float = 0.0   # >0: enter with a limit order this many ATRs better than the signal close
    limit_valid_min: int = 60       # minutes a limit order stays live
    entry_delay_min: int = 0        # stress test: execute signals this many minutes late
    daily_loss_usd: float = 0.0     # flatten + stop for the day at this $ loss (closed + open), 0=off
    daily_target_usd: float = 0.0   # stop opening trades for the day at this $ profit (closed), 0=off
    max_trades_day: int = 30
    max_consec_losses: int = 4
    cooldown_min: int = 60
    be_r: float = 0.8
    be_lock: float = 0.10
    trail_start_r: float = 1.0
    trail_atr: float = 1.0
    max_bars: int = 24
    close_on_opposite: bool = True
    max_spread: float = 0.50
    use_session: bool = True
    sess_start: int = 9
    sess_end: int = 23
    friday_close: bool = True
    friday_hour: int = 21
    # account / costs
    spread: float = 0.30            # fixed spread ($) when spread_profile is None
    spread_profile: object = None   # DataFrame [year, minute_of_day(UTC)] -> spread ($), see load_spread_profile
    spread_scale: float = 1.0       # multiply the profile (e.g. to model a standard-account markup)
    commission_per_lot: float = 0.0 # round-turn commission, $ per 1.00 lot
    slippage: float = 0.05
    contract: float = 100.0
    lot_step: float = 0.01
    lot_min: float = 0.01
    leverage: float = 20.0


def load_spread_profile(path):
    """Average real spread by (year, UTC minute of day) from tick statistics CSV."""
    df = pd.read_csv(path)
    return df.pivot(index="minute_of_day", columns="year", values="avg_spread_price")


def spread_series(index, p):
    """Per-M1-bar spread ($) for a server-time index."""
    if p.spread_profile is None:
        return np.full(len(index), p.spread)
    ny = (index - pd.Timedelta(hours=7)).tz_localize("America/New_York", ambiguous=False,
                                                       nonexistent="shift_forward")
    utc = ny.tz_convert("UTC")
    mod = (utc.hour * 60 + utc.minute).to_numpy()
    prof = p.spread_profile
    years = np.clip(utc.year.to_numpy(), prof.columns.min(), prof.columns.max())
    out = np.empty(len(index))
    for y in np.unique(years):
        col = prof[y].reindex(range(1440)).interpolate().bfill().ffill().to_numpy()
        m = years == y
        out[m] = col[mod[m]]
    return out * p.spread_scale


# ---------------------------------------------------------------- indicators (MT5 formulas)
def ema(x, n):
    return x.ewm(span=n, adjust=False).mean()


def rsi(c, n):
    d = c.diff()
    ag = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    al = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + ag / al.replace(0, np.nan))


def true_range(h, l, c):
    pc = c.shift()
    return pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)


def adx_mt5(h, l, c, n):
    up = h.diff().clip(lower=0)
    dn = (-l.diff()).clip(lower=0)
    p = np.where(up > dn, up, 0.0)
    m = np.where(dn > up, dn, 0.0)
    tr = true_range(h, l, c).replace(0, np.nan)
    pd_ = pd.Series(100 * p, index=h.index) / tr
    nd_ = pd.Series(100 * m, index=h.index) / tr
    pdi = ema(pd_.fillna(0), n)
    ndi = ema(nd_.fillna(0), n)
    s = (pdi + ndi).replace(0, np.nan)
    dx = (100 * (pdi - ndi).abs() / s).fillna(0)
    return ema(dx, n), pdi, ndi


def stoch(h, l, c, k, d, slow):
    ll = l.rolling(k).min()
    hh = h.rolling(k).max()
    num = (c - ll).rolling(slow).sum()
    den = (hh - ll).rolling(slow).sum().replace(0, np.nan)
    kk = (100 * num / den).fillna(100.0)
    return kk, kk.rolling(d).mean()


def resample(m1, minutes):
    return (m1.resample(f"{minutes}min", label="left", closed="left")
            .agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna())


# ---------------------------------------------------------------- signals
def sig_confluence(b, p, name=None):
    c, o, h, l = b["close"], b["open"], b["high"], b["low"]
    ef, es = ema(c, p.ema_fast), ema(c, p.ema_slow)
    r = rsi(c, p.rsi_n)
    macd = ema(c, p.macd[0]) - ema(c, p.macd[1])
    hist = macd - macd.rolling(p.macd[2]).mean()
    adx, pdi, ndi = adx_mt5(h, l, c, p.adx_n)
    a = true_range(h, l, c).rolling(p.atr_n).mean()
    bm = c.rolling(p.bb_n).mean()
    sd = c.rolling(p.bb_n).std(ddof=0)
    bu, bl = bm + p.bb_dev * sd, bm - p.bb_dev * sd
    k, d = stoch(h, l, c, *p.sto)
    pv = lambda s: s.shift(1)
    adxok = adx >= p.adx_min
    rng, body = h - l, c - o

    L = [ef > es, (r > 50) & (r < p.rsi_buy_max) & (r > pv(r)), (hist > 0) & (hist > pv(hist)),
         adxok & (pdi > ndi), (c > bm) & (c < bu), (k > d) & (k < p.sto_ob),
         (rng > 0) & (body > 0) & (body >= 0.35 * rng)]
    S = [ef < es, (r < 50) & (r > p.rsi_sell_min) & (r < pv(r)), (hist < 0) & (hist < pv(hist)),
         adxok & (ndi > pdi), (c < bm) & (c > bl), (k < d) & (k > p.sto_os),
         (rng > 0) & (body < 0) & (-body >= 0.35 * rng)]
    sl = sum(x.astype(int) for x in L)
    ss = sum(x.astype(int) for x in S)
    trig_l = ((ef > es) & (l <= ef + 0.25 * a) & (c > ef)) | ((pv(ef) <= pv(es)) & (ef > es)) | \
             ((pv(k) <= pv(d)) & (k > d) & (pv(k) < 50))
    trig_s = ((ef < es) & (h >= ef - 0.25 * a) & (c < ef)) | ((pv(ef) >= pv(es)) & (ef < es)) | \
             ((pv(k) >= pv(d)) & (k < d) & (pv(k) > 50))
    dirn = np.where((sl >= p.min_score) & (sl > ss) & trig_l, 1,
                    np.where((ss >= p.min_score) & (ss > sl) & trig_s, -1, 0))
    if p.require_adx:
        dirn = np.where(adxok, dirn, 0)
    dirn[:300] = 0  # indicator warm-up
    out = pd.DataFrame({"dir": dirn, "score": np.maximum(sl, ss), "atr": a}, index=b.index)
    return out


def tf_signals(b, p, name):
    if p.strategy == "confluence":
        return sig_confluence(b, p, name)
    import strategies
    return strategies.STRATEGIES[p.strategy](b, p, name)


# ---------------------------------------------------------------- simulation
class Pos:
    __slots__ = ("pid", "d", "entry", "sl", "tp", "lots", "ot", "tf", "R", "risk", "score", "trend", "tmin")


def run(m1, p, start_balance, quiet=False):
    T = (m1.index.values.astype("datetime64[m]").astype(np.int64))
    O, H, Lo, C = (m1[k].to_numpy() for k in ("open", "high", "low", "close"))
    DAY = T // 1440
    HR = (T // 60) % 24
    DOW = m1.index.dayofweek.to_numpy()
    N = len(T)

    # trend (H4) by bar close time
    hb = resample(m1, p.trend_min)
    tf_, ts_ = ema(hb.close, p.trend_fast), ema(hb.close, p.trend_slow)
    trend = np.where((hb.close > ts_) & (tf_ > ts_), 1, np.where((hb.close < ts_) & (tf_ < ts_), -1, 0))
    trend[:p.trend_slow] = 0
    trend_close = hb.index.values.astype("datetime64[m]").astype(np.int64) + p.trend_min

    sigmap = {}               # m1 index -> list of (tf_idx, dir, score, atr)
    exitmap = {}              # m1 index -> list of (tf_idx, side to close)
    tgtmap = {}               # m1 index -> list of (tf_idx, new limit take-profit level)
    atr_at = []               # per TF: ATR of last closed bar at each M1 bar
    for ti, (name, mins) in enumerate(TF_LIST):
        b = resample(m1, mins)
        s = tf_signals(b, p, name)
        close_t = b.index.values.astype("datetime64[m]").astype(np.int64) + mins
        pos = np.searchsorted(close_t, T, side="right") - 1
        atr_arr = s["atr"].to_numpy()
        atr_at.append(np.where(pos >= 0, atr_arr[np.clip(pos, 0, None)], np.nan))
        if not p.use_tf.get(name, False):
            continue
        entry_idx = np.searchsorted(T, close_t + p.entry_delay_min, side="left")
        last = {}
        for j, ei in enumerate(entry_idx):
            if ei < N:
                last[ei] = j       # EA only sees the latest closed bar on that tick
        dirs, scores = s["dir"].to_numpy(), s["score"].to_numpy()
        closes = b["close"].to_numpy()
        if "xl" in s:   # strategy-defined exits at bar close
            xl, xs = s["xl"].to_numpy(bool), s["xs"].to_numpy(bool)
            for ei, j in last.items():
                if xl[j]:
                    exitmap.setdefault(ei, []).append((ti, 1))
                if xs[j]:
                    exitmap.setdefault(ei, []).append((ti, -1))
        tg = s["tgt"].to_numpy() if "tgt" in s else None
        if tg is not None:
            for ei, j in last.items():
                if tg[j] == tg[j]:
                    tgtmap.setdefault(ei, []).append((ti, tg[j]))
        for ei, j in last.items():
            if dirs[j] != 0:
                tpos = np.searchsorted(trend_close, T[ei], side="right") - 1
                tr = trend[tpos] if tpos >= 0 else 0
                if p.use_trend and tr != dirs[j]:
                    continue
                sigmap.setdefault(ei, []).append((ti, int(dirs[j]), int(scores[j]), atr_arr[j], int(tr),
                                                  tg[j] if tg is not None else np.nan, closes[j]))

    SP = spread_series(m1.index, p)
    sp, slip, cs = SP[0], p.slippage, p.contract
    comm = p.commission_per_lot
    balance = start_balance
    positions = []
    trades = []
    pid = [0]
    st = dict(day=-1, start=balance, closed=0.0, n=0, consec=0, last_loss=-10**12, halted=False)
    refused = [0]

    def pnl_of(ps, bid):
        return ((bid - ps.entry) if ps.d > 0 else (ps.entry - (bid + sp))) * cs * ps.lots

    def close(ps, exit_px, t, reason):
        nonlocal balance
        pnl = ((exit_px - ps.entry) if ps.d > 0 else (ps.entry - exit_px)) * cs * ps.lots - comm * ps.lots
        balance += pnl
        st["closed"] += pnl
        if pnl < 0:
            st["consec"] += 1
            st["last_loss"] = t
        elif pnl > 0:
            st["consec"] = 0
        trades.append(dict(pid=ps.pid, tf=TF_LIST[ps.tf][0], dir=ps.d, open_t=ps.ot, close_t=t, entry=ps.entry,
                           exit=exit_px, lots=ps.lots, pnl=pnl, r=pnl / ps.risk if ps.risk else 0.0,
                           score=ps.score, trend=ps.trend, reason=reason, bal=balance))
        positions.remove(ps)

    def market_close(ps, bid, t, reason):
        px = bid - slip if ps.d > 0 else bid + sp + slip
        close(ps, px, t, reason)

    def manage(bid, i):
        for ps in positions:
            a = atr_at[ps.tf][i]
            if not a > 0:
                continue
            step = max(a * 0.05, 0.05)
            if ps.d > 0:
                prof = bid - ps.entry
                nsl = ps.sl
                if p.be_r > 0 and prof >= p.be_r * ps.R:
                    nsl = max(nsl, ps.entry + p.be_lock)
                if p.trail_start_r > 0 and prof >= p.trail_start_r * ps.R:
                    nsl = max(nsl, bid - a * p.trail_atr)
                if nsl > ps.sl + step and bid - nsl > 0:
                    ps.sl = nsl
            else:
                ask = bid + sp
                prof = ps.entry - ask
                nsl = ps.sl
                if p.be_r > 0 and prof >= p.be_r * ps.R:
                    nsl = min(nsl, ps.entry - p.be_lock)
                if p.trail_start_r > 0 and prof >= p.trail_start_r * ps.R:
                    nsl = min(nsl, ask + a * p.trail_atr)
                if nsl < ps.sl - step and nsl - ask > 0:
                    ps.sl = nsl

    def daily_loss_check(bid, t):
        fl = sum(pnl_of(ps, bid) for ps in positions)
        if p.daily_loss_usd > 0 and st["closed"] + fl <= -p.daily_loss_usd:
            for ps in list(positions):
                market_close(ps, bid, t, "daily_loss")
            st["halted"] = True
            return
        if p.daily_target_usd > 0 and st["closed"] >= p.daily_target_usd:
            st["halted"] = True
        if p.max_daily_loss_pct <= 0:
            return
        if st["closed"] + fl <= -st["start"] * p.max_daily_loss_pct / 100:
            for ps in list(positions):
                market_close(ps, bid, t, "daily_loss")
            st["halted"] = True

    pending = {}

    def open_pos(ti, d, score, a, tr, tgt, entry, t, o):
        sl_dist = max(a * p.sl_atr, p.min_sl, sp)
        equity = balance + sum(pnl_of(x, o) for x in positions)
        if p.fixed_lots > 0:
            lots = p.fixed_lots
            if p.fixed_lot_max_risk_pct > 0 and \
                    lots * (sl_dist * cs + comm) > equity * p.fixed_lot_max_risk_pct / 100:
                refused[0] += 1
                return False
        else:
            lots = equity * p.risk_pct / 100 / (sl_dist * cs)
        lots = min(math.floor(lots / p.lot_step + 1e-9) * p.lot_step, p.max_lots)
        used = sum(x.lots * cs * x.entry / p.leverage for x in positions)
        need = lots * cs * entry / p.leverage
        free = equity - used
        if need > 0.9 * free and need > 0:
            lots = math.floor(lots * 0.9 * free / need / p.lot_step + 1e-9) * p.lot_step
        if lots < p.lot_min - 1e-12:
            refused[0] += 1
            return False
        ps = Pos()
        pid[0] += 1
        ps.pid, ps.d, ps.entry, ps.lots, ps.ot, ps.tf = pid[0], d, entry, round(lots, 3), t, ti
        ps.R = sl_dist
        ps.sl = entry - d * sl_dist
        ps.tp = entry + d * sl_dist * p.rr
        ps.risk = sl_dist * cs * ps.lots + comm * ps.lots
        ps.score, ps.trend = score, tr
        if tgt == tgt and (tgt - entry) * d > 0:
            ps.tp = tgt
        positions.append(ps)
        st["n"] += 1
        return True

    def in_session(hr):
        if not p.use_session or p.sess_start == p.sess_end:
            return True
        if p.sess_start < p.sess_end:
            return p.sess_start <= hr < p.sess_end
        return hr >= p.sess_start or hr < p.sess_end

    for i in range(N):
        t, o = T[i], O[i]
        sp = SP[i]
        if DAY[i] != st["day"]:
            st.update(day=DAY[i], start=balance, closed=0.0, n=0, consec=0, last_loss=-10**12, halted=False)
        fri = p.friday_close and DOW[i] == 4 and HR[i] >= p.friday_hour

        if p.daily_target_usd > 0 and st["closed"] >= p.daily_target_usd:
            st["halted"] = True
        if positions:
            if fri:
                for ps in list(positions):
                    market_close(ps, o, t, "friday")
            if p.max_bars > 0:
                for ps in list(positions):
                    if t - ps.ot >= p.max_bars * TF_LIST[ps.tf][1]:
                        market_close(ps, o, t, "time")
            manage(o, i)
            daily_loss_check(o, t)

        xs_ = exitmap.get(i)
        if xs_:
            for ti, side in xs_:
                for ps in [x for x in positions if x.tf == ti and x.d == side]:
                    market_close(ps, o, t, "exit_signal")
                if ti in pending and pending[ti][0] == side:     # bounce already happened: cancel the limit
                    del pending[ti]

        tg_ = tgtmap.get(i)
        if tg_ and positions:
            for ti, lvl in tg_:
                for ps in positions:
                    if ps.tf == ti:
                        ps.tp = lvl

        sigs = sigmap.get(i)
        if sigs:
            can = not st["halted"] and sp <= p.max_spread and not fri and in_session(HR[i])
            if can and p.max_trades_day > 0 and st["n"] >= p.max_trades_day:
                can = False
            if can and p.max_consec_losses > 0 and st["consec"] >= p.max_consec_losses and \
                    t - st["last_loss"] < p.cooldown_min:
                can = False
            for ti, d, score, a, tr, tgt, sig_close in sigs:
                if p.close_on_opposite:
                    for ps in [x for x in positions if x.tf == ti and x.d == -d]:
                        market_close(ps, o, t, "opposite")
                if not can or not a > 0:
                    continue
                if sum(1 for x in positions if x.tf == ti) >= p.max_pos_tf or len(positions) >= p.max_pos_total:
                    continue
                if p.limit_offset_atr > 0:         # place a limit order instead of buying at market
                    pending[ti] = (d, score, a, tr, tgt, sig_close - d * p.limit_offset_atr * a, t + p.limit_valid_min)
                    continue
                entry = (o + sp + slip) if d > 0 else (o - slip)
                open_pos(ti, d, score, a, tr, tgt, entry, t, o)

        if pending:
            for ti in list(pending):
                d, score, a, tr, tgt, px, exp = pending[ti]
                if t > exp or sum(1 for x in positions if x.tf == ti) >= p.max_pos_tf:
                    del pending[ti]
                    continue
                if d > 0 and Lo[i] + sp <= px:           # ask touched the buy limit
                    del pending[ti]
                    open_pos(ti, d, score, a, tr, tgt, min(px, o + sp), t, o)
                elif d < 0 and H[i] >= px:               # bid touched the sell limit
                    del pending[ti]
                    open_pos(ti, d, score, a, tr, tgt, max(px, o), t, o)

        if positions:
            h, l, c = H[i], Lo[i], C[i]
            for ps in list(positions):
                if ps.d > 0:
                    if l <= ps.sl:
                        close(ps, min(o, ps.sl) - slip, t, "sl" if ps.sl < ps.entry else "trail/be")
                    elif h >= ps.tp:
                        close(ps, o if o >= ps.tp else ps.tp, t, "tp")
                else:
                    if h + sp >= ps.sl:
                        close(ps, max(o + sp, ps.sl) + slip, t, "sl" if ps.sl > ps.entry else "trail/be")
                    elif l + sp <= ps.tp:
                        close(ps, o + sp if o + sp <= ps.tp else ps.tp, t, "tp")
            manage(c, i)
            daily_loss_check(c, t)

    for ps in list(positions):
        market_close(ps, C[-1], T[-1], "end")
    if not quiet:
        print(f"refused (lot below minimum): {refused[0]}")
    return trades, balance, refused[0]


# ---------------------------------------------------------------- reporting
def tstr(m):
    return pd.Timestamp(int(m) * 60, unit="s").strftime("%Y.%m.%d %H:%M:%S")


def session_of(m):
    hr = (int(m) // 60) % 24
    return "Asia" if hr < 9 else "London" if hr < 15 else "NewYork" if hr < 20 else "Late"


def write_trades_csv(trades, path):
    """Same columns as the live EA log format expected by bt_analyze.py."""
    cols = ["time", "event", "position_id", "profit_net", "r_multiple", "setup", "regime", "session",
            "confidence", "exit_reason"]
    rows = []
    for tr in trades:
        regime = {1: "trend_up", -1: "trend_down", 0: "no_filter"}[tr["trend"]]
        conf = round(tr["score"] / 7 * 100)
        base = dict(position_id=tr["pid"], setup=f"{tr['tf']}_{'BUY' if tr['dir'] > 0 else 'SELL'}",
                    regime=regime, session=session_of(tr["open_t"]), confidence=conf)
        rows.append(dict(base, time=tstr(tr["open_t"]), event="OPEN", profit_net="", r_multiple="", exit_reason=""))
        rows.append(dict(base, time=tstr(tr["close_t"]), event="CLOSE", profit_net=f"{tr['pnl']:.2f}",
                         r_multiple=f"{tr['r']:.3f}", exit_reason=tr["reason"]))
    rows.sort(key=lambda r: (r["time"], r["event"] != "OPEN"))
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def summary(trades, start):
    if not trades:
        return dict(n=0)
    pnl = np.array([t["pnl"] for t in trades])
    eq = start + np.cumsum(pnl)
    peak = np.maximum.accumulate(np.concatenate([[start], eq]))[1:]
    dd = ((peak - eq) / peak).max() * 100
    w, l = pnl[pnl > 0].sum(), -pnl[pnl <= 0].sum()
    return dict(n=len(pnl), net=pnl.sum(), ret=pnl.sum() / start * 100, win=(pnl > 0).mean() * 100,
                pf=w / l if l else float("inf"), avg_r=np.mean([t["r"] for t in trades]), mdd=dd,
                final=eq[-1])


def main():
    a = argparse.ArgumentParser()
    a.add_argument("data")
    a.add_argument("--start", type=float, default=10000)
    a.add_argument("--spread", type=float, default=0.30)
    a.add_argument("--slippage", type=float, default=0.05)
    a.add_argument("--risk", type=float, default=1.0)
    a.add_argument("--lot-step", type=float, default=0.01)
    a.add_argument("--lot-min", type=float, default=0.01)
    a.add_argument("--from", dest="dfrom")
    a.add_argument("--to", dest="dto")
    a.add_argument("--out", default="trades.csv")
    o = a.parse_args()
    m1 = pd.read_pickle(o.data)
    if o.dfrom:
        m1 = m1[m1.index >= o.dfrom]
    if o.dto:
        m1 = m1[m1.index < o.dto]
    p = Params(spread=o.spread, slippage=o.slippage, risk_pct=o.risk, lot_step=o.lot_step, lot_min=o.lot_min)
    trades, bal, _ = run(m1, p, o.start)
    write_trades_csv(trades, o.out)
    s = summary(trades, o.start)
    print({k: round(v, 3) if isinstance(v, float) else v for k, v in s.items()})


if __name__ == "__main__":
    main()

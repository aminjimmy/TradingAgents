"""Chart features for each H1 bar, using only information available at that bar's close."""
import numpy as np
import pandas as pd

from gold_scalper_bt import adx_mt5, ema, rsi, stoch, true_range


def h1_features(h1):
    c, h, l, o = h1["close"], h1["high"], h1["low"], h1["open"]
    atr = true_range(h, l, c).rolling(14).mean()
    f = pd.DataFrame(index=h1.index)
    f["rsi2"] = rsi(c, 2)
    f["rsi2_prev"] = f["rsi2"].shift(1)
    f["rsi14"] = rsi(c, 14)
    f["rsi14_h4"] = rsi(c, 56)                         # ~ RSI(14) on H4
    f["rsi14_d1"] = rsi(c, 14 * 24)                    # ~ RSI(14) on D1
    for n in (5, 20, 50, 200):
        f[f"dist_ema{n}"] = (c - ema(c, n)) / atr
    f["ema50_slope"] = (ema(c, 50) - ema(c, 50).shift(5)) / atr
    f["ema200_slope"] = (ema(c, 200) - ema(c, 200).shift(10)) / atr
    f["stop_vs_atr"] = 10.0 / atr                     # the user's fixed $10 stop measured in ATRs (scale-free)
    f["atr_ratio_50"] = atr / atr.rolling(50).mean()
    f["atr_ratio_500"] = atr / atr.rolling(500).mean()
    adx, pdi, ndi = adx_mt5(h, l, c, 14)
    f["adx"] = adx
    f["di_diff"] = pdi - ndi
    m, sd = c.rolling(20).mean(), c.rolling(20).std(ddof=0)
    f["bb_pos"] = (c - m) / (2 * sd).replace(0, np.nan)
    f["bb_width"] = 4 * sd / atr
    k, d = stoch(h, l, c, 5, 3, 3)
    f["stoch_k"] = k
    f["stoch_kd"] = k - d
    mac = ema(c, 12) - ema(c, 26)
    f["macd_hist"] = (mac - mac.rolling(9).mean()) / atr
    f["macd_hist_chg"] = f["macd_hist"] - f["macd_hist"].shift(1)
    for n in (1, 3, 6, 12, 24, 72):
        f[f"ret_{n}"] = (c - c.shift(n)) / atr
    rng = (h - l).replace(0, np.nan)
    f["body"] = (c - o) / rng
    f["upper_wick"] = (h - np.maximum(o, c)) / rng
    f["lower_wick"] = (np.minimum(o, c) - l) / rng
    f["range_atr"] = (h - l) / atr
    down = (c < c.shift(1)).astype(int)
    f["down_streak"] = down.groupby((down == 0).cumsum()).cumsum()
    up = (c > c.shift(1)).astype(int)
    f["up_streak"] = up.groupby((up == 0).cumsum()).cumsum()
    hh24, ll24 = h.rolling(24).max(), l.rolling(24).min()
    f["pos_24h"] = (c - ll24) / (hh24 - ll24).replace(0, np.nan)
    f["range24_atr"] = (hh24 - ll24) / atr
    day = h1.index.normalize()
    dh = h.groupby(day).max().shift(1).reindex(day).to_numpy()
    dl = l.groupby(day).min().shift(1).reindex(day).to_numpy()
    f["dist_prev_high"] = (c - dh) / atr
    f["dist_prev_low"] = (c - dl) / atr
    dclose = c.resample("1D").last().dropna()
    dtrend = ((dclose - ema(dclose, 50)) / dclose * 100).shift(1)
    f["d1_trend_pct"] = dtrend.reindex(day).to_numpy()
    f["h4_trend"] = (ema(c, 200) - ema(c, 800)) / atr    # ~ EMA50 vs EMA200 on H4
    hr = h1.index.hour + 1                               # hour at which the signal bar closes (server)
    f["hour_sin"], f["hour_cos"] = np.sin(2 * np.pi * hr / 24), np.cos(2 * np.pi * hr / 24)
    f["dow"] = h1.index.dayofweek
    return f


# features whose meaning flips for short trades (multiplied by direction so "+" always = in our favour)
DIRECTIONAL = ["dist_ema5", "dist_ema20", "dist_ema50", "dist_ema200", "ema50_slope", "ema200_slope", "di_diff",
               "bb_pos", "stoch_kd", "macd_hist", "macd_hist_chg", "ret_1", "ret_3", "ret_6", "ret_12", "ret_24",
               "ret_72", "body", "d1_trend_pct", "h4_trend"]
# bounded 0-100 / 0-1 features mirrored for shorts
MIRROR_100 = ["rsi2", "rsi2_prev", "rsi14", "rsi14_h4", "rsi14_d1", "stoch_k"]
MIRROR_1 = ["pos_24h"]


def oriented(feat_rows, dirs):
    x = feat_rows.copy()
    d = np.asarray(dirs)
    for col in DIRECTIONAL:
        x[col] = x[col] * d
    for col in MIRROR_100:
        x[col] = np.where(d > 0, x[col], 100 - x[col])
    for col in MIRROR_1:
        x[col] = np.where(d > 0, x[col], 1 - x[col])
    lw, uw = x["lower_wick"].copy(), x["upper_wick"].copy()
    x["lower_wick"] = np.where(d > 0, lw, uw)            # "rejection" wick in our favour
    x["upper_wick"] = np.where(d > 0, uw, lw)
    hi, lo = x["dist_prev_high"].copy(), x["dist_prev_low"].copy()
    x["dist_prev_high"] = np.where(d > 0, hi, -lo)
    x["dist_prev_low"] = np.where(d > 0, lo, -hi)
    s1, s2 = x["down_streak"].copy(), x["up_streak"].copy()
    x["down_streak"] = np.where(d > 0, s1, s2)           # streak against us
    x["up_streak"] = np.where(d > 0, s2, s1)
    x["is_long"] = (d > 0).astype(int)
    return x


# ---------------------------------------------------------------- macro / cross-asset features
MACRO_DIR = __import__("os").path.join(__import__("os").path.dirname(__file__), "macro_data")


def _series(name):
    import os
    df = pd.read_csv(os.path.join(MACRO_DIR, f"{name}.csv"))
    s = pd.to_numeric(df.iloc[:, 1], errors="coerce")
    s.index = pd.to_datetime(df.iloc[:, 0])
    return s.dropna().sort_index()


def macro_daily():
    """One row per US date, built only from that date's close (shifted later to avoid lookahead)."""
    dxy, broad = _series("Y_DXY"), _series("DTWEXBGS")
    ry, n10, n2, bei = _series("DFII10"), _series("DGS10"), _series("DGS2"), _series("T10YIE")
    vix, oil, spx = _series("VIXCLS"), _series("Y_OIL"), _series("Y_SPX")
    idx = dxy.index.union(ry.index).union(vix.index)
    a = lambda s: s.reindex(idx).ffill()
    dxy, broad, ry, n10, n2, bei, vix, oil, spx = map(a, (dxy, broad, ry, n10, n2, bei, vix, oil, spx))
    m = pd.DataFrame(index=idx)
    for n in (1, 5, 20):
        m[f"dxy_chg{n}"] = dxy.pct_change(n) * 100
    m["dxy_vs_ema50"] = (dxy / ema(dxy, 50) - 1) * 100
    m["broad_usd_chg20"] = broad.pct_change(20) * 100
    eur = _series("DEXUSEU").reindex(idx).ffill()
    m["eurusd_chg20"] = eur.pct_change(20, fill_method=None) * 100   # MT5-available dollar proxy (inverse)
    m["real_yield"] = ry
    m["real_yield_chg5"] = (ry - ry.shift(5)) * 100          # basis points
    m["real_yield_chg20"] = (ry - ry.shift(20)) * 100
    m["nominal10_chg5"] = (n10 - n10.shift(5)) * 100
    m["nominal10_chg20"] = (n10 - n10.shift(20)) * 100
    m["breakeven_chg20"] = (bei - bei.shift(20)) * 100
    m["curve_2s10s"] = n10 - n2
    m["vix"] = vix
    m["vix_chg5"] = vix - vix.shift(5)
    m["oil_chg20"] = oil.pct_change(20) * 100
    m["spx_chg20"] = spx.pct_change(20) * 100
    fomc = _series("FOMC_DATES").index
    pos = np.searchsorted(fomc.values, idx.values, side="right") - 1
    m["days_since_fomc"] = np.where(pos >= 0, (idx.values - fomc.values[np.clip(pos, 0, None)]) /
                                    np.timedelta64(1, "D"), np.nan)
    return m


def macro_features(h1_index):
    """Align daily macro rows to H1 bars using only the PREVIOUS completed US trading day."""
    m = macro_daily()
    key = pd.DataFrame({"t": h1_index.normalize() - pd.Timedelta(days=1)}, index=h1_index)
    out = pd.merge_asof(key.sort_values("t"), m.rename_axis("t").reset_index(), on="t", direction="backward")
    out.index = key.sort_values("t").index
    return out.drop(columns="t").reindex(h1_index)


# macro features where "good for a gold LONG" has a sign: multiplied by -1 for a long so "+" = tailwind
MACRO_AGAINST_GOLD = ["dxy_chg1", "dxy_chg5", "dxy_chg20", "dxy_vs_ema50", "broad_usd_chg20",
                      "real_yield_chg5", "real_yield_chg20", "nominal10_chg5", "nominal10_chg20"]
MACRO_FOR_GOLD = ["breakeven_chg20", "vix_chg5"]


def orient_macro(x, dirs):
    d = np.asarray(dirs)
    x = x.copy()
    for col in MACRO_AGAINST_GOLD:
        if col in x:
            x[col] = -x[col] * d
    for col in MACRO_FOR_GOLD:
        if col in x:
            x[col] = x[col] * d
    return x

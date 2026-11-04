#!/usr/bin/env python3
"""Do trades earn more in high volatility, consistently? (usage: python3 volatility_sizing_check.py xau_m1.pkl)"""
import sys, numpy as np, pandas as pd
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
from gold_scalper_bt import resample, true_range, run
from robustness import preset
from claude_bot import grow
m1 = pd.read_pickle(sys.argv[1]); h1 = resample(m1, 60)
atr = true_range(h1.high, h1.low, h1.close).rolling(14).mean()
ratio = atr / atr.rolling(500).mean()          # volatility vs its ~1-month norm (scale-free)
tr, _, _ = run(m1, preset(), 1e6, quiet=True); df = pd.DataFrame(tr)
t = pd.to_datetime(df.open_t * 60, unit="s"); sig = (t - pd.Timedelta(hours=1)).dt.floor("h")
df["atr$"] = atr.reindex(sig).to_numpy(); df["vr"] = ratio.reindex(sig).to_numpy()
df["half"] = np.where(t.dt.year < 2024, "2020-23", "2024-26"); df["y"] = t.dt.year
for col, lab in (("atr$", "H1 ATR in $ (absolute)"), ("vr", "ATR vs its own recent norm (relative)")):
    print(f"\nby {lab}: avg R per trade [n]")
    for h in ("2020-23", "2024-26"):
        d = df[df.half == h]; q = d[col].quantile([1/3, 2/3]).to_numpy()
        b = pd.cut(d[col], [-np.inf, q[0], q[1], np.inf], labels=["low", "mid", "high"])
        g = d.groupby(b, observed=True).r.agg(["mean", "count"])
        print(f"  {h}: " + "  ".join(f"{k}: {v['mean']:+.3f} [{int(v['count'])}]" for k, v in g.iterrows()))
# relative-vol sizing rule: risk x1.5 when vr > 1.2, x0.5 when vr < 0.8 (causal: known at entry)
mult = np.where(df.vr > 1.2, 1.5, np.where(df.vr < 0.8, 0.5, 1.0))
for h, m in (("2020-23", df.half == "2020-23"), ("2024-26", df.half == "2024-26"), ("all", df.half.notna())):
    base = df.r[m].sum(); scaled = (df.r * mult)[m].sum(); avg_m = mult[m.to_numpy()].mean()
    print(f"{h}: flat sizing {base:+.1f}R | vol-scaled {scaled:+.1f}R (avg size x{avg_m:.2f}, per unit risk {scaled/avg_m:+.1f}R)")

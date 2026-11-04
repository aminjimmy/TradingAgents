import sys, itertools, pandas as pd, numpy as np
from multiprocessing import Pool
sys.path.insert(0, __import__("os").path.dirname(__file__))
from gold_scalper_bt import run, Params
m1 = pd.read_pickle(sys.argv[1])
IS = m1[m1.index < "2024-01-01"]
ALLTF = {"M5":True,"M15":True,"M30":True,"H1":True}
def tfs(*on): return {k:(k in on) for k in ALLTF}
V = {
 "base":            {},
 "base_zero_cost":  dict(spread=0.0, slippage=0.0),
 "H1_only":         dict(use_tf=tfs("H1")),
 "M30_H1":          dict(use_tf=tfs("M30","H1")),
 "M15_M30_H1":      dict(use_tf=tfs("M15","M30","H1")),
 "score6":          dict(min_score=6),
 "score7":          dict(min_score=7),
 "rr1_noBE":        dict(rr=1.0, be_r=0, trail_start_r=0),
 "rr2_noBE":        dict(rr=2.0, be_r=0, trail_start_r=0),
 "rr3_trail":       dict(rr=3.0, be_r=0, trail_start_r=1.0, trail_atr=1.5),
 "sl2.5_rr1.5":     dict(sl_atr=2.5),
 "no_trend_filter": dict(use_trend=False),
 "trendH1":         dict(trend_min=60),
 "adx25":           dict(adx_min=25),
 "london_ny_only":  dict(sess_start=10, sess_end=19),
 "no_time_exit":    dict(max_bars=0),
}
def job(name):
    p = Params(fixed_lots=0.10, max_daily_loss_pct=0, max_trades_day=0, max_consec_losses=0, **V[name])
    tr,_,_ = run(IS, p, 1e6, quiet=True)
    r = np.array([t["r"] for t in tr]); pnl=np.array([t["pnl"] for t in tr])
    pf = pnl[pnl>0].sum()/-pnl[pnl<=0].sum()
    return name, len(r), r.mean(), pf
with Pool(4) as pool:
    for name,n,ar,pf in pool.map(job, V):
        print(f"{name:18s} n={n:6d} avgR={ar:+.3f} PF={pf:.2f}")

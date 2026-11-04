#!/usr/bin/env python3
"""Train the bot to read the chart: a walk-forward machine-learning filter on RSI(2) pullback setups.

1. Candidates: every H1 bar with RSI(2) < 15 above EMA200 (long) or RSI(2) > 85 below EMA200 (short).
2. Label: did that trade win, with the user's rules (0.01 lot, $10 stop, $30 target, EMA5 exit,
   24h, real raw-account costs)? Each candidate is simulated on its own.
3. Features: ~45 chart readings at the signal bar's close (ml_features.py), oriented so "+" = in our favour.
4. Walk-forward: for each test year 2022..2026 the model is trained ONLY on earlier years (with a purge
   so no training trade overlaps the test year), then picks trades in the unseen year.
5. The picked trades are run through the normal EA rules (one position per TF) and compared with the
   current hand-made plan (RSI(2)<10 + daily trend), all candidates, and random picks of the same size.

usage: python3 ml_train.py xau_m1.pkl
"""
import os
import sys
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gold_scalper_bt import Params, ema, resample, rsi, run  # noqa: E402
from ml_features import h1_features, oriented  # noqa: E402
from real_spread_test import costs, ea  # noqa: E402

import lightgbm as lgb  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.pipeline import make_pipeline  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402
from sklearn.impute import SimpleImputer  # noqa: E402

TEST_YEARS = [2022, 2023, 2024, 2025, 2026]
KEEP = 0.5          # fraction of candidates the model keeps (fixed in advance)


def user_params(**kw):
    p = dict(ea("v1.10"), **costs("raw"))
    p.update(fixed_lots=0.01, sl_atr=0.0, min_sl=10.0, rr=3.0, max_daily_loss_pct=0, use_session=False,
             max_trades_day=0, max_consec_losses=0)
    p.update(kw)
    return Params(**p)


def label_candidates(m1, cand):
    """Simulate every candidate independently (unlimited concurrent positions)."""
    p = user_params(strategy="external", sargs=dict(signals={"H1": cand}), max_pos_tf=100000,
                    max_pos_total=100000, close_on_opposite=False)
    tr, _, _ = run(m1, p, 1e7, quiet=True)
    df = pd.DataFrame(tr)
    close_t = (cand.index + pd.Timedelta(hours=1)).values.astype("datetime64[m]").astype(np.int64)
    j = np.searchsorted(close_t, df.open_t.to_numpy(), side="right") - 1
    df["bar"] = cand.index[j]
    df = df.drop_duplicates("bar").set_index("bar")
    return df


def lgbm():
    return lgb.LGBMClassifier(n_estimators=300, learning_rate=0.03, num_leaves=8, min_child_samples=40,
                              subsample=0.8, subsample_freq=1, colsample_bytree=0.7, reg_lambda=5.0, verbose=-1)


def logreg():
    return make_pipeline(SimpleImputer(), StandardScaler(), LogisticRegression(C=0.1, max_iter=2000))


def oof_preds(make, X, y):
    """Out-of-fold predictions on the training years (5 contiguous blocks)."""
    idx = np.array_split(np.arange(len(X)), 5)
    oof = np.full(len(X), np.nan)
    for k in range(5):
        tr = np.concatenate([idx[i] for i in range(5) if i != k])
        m = make().fit(X.iloc[tr], y[tr])
        oof[idx[k]] = m.predict_proba(X.iloc[idx[k]])[:, 1]
    return oof


def adaptive_keep(history, preds, keep, window=300):
    """Keep a test setup if its score is in the top `keep` share of the last `window` scores (causal)."""
    hist = list(history[-window:])
    out = np.zeros(len(preds), bool)
    for i, pr in enumerate(preds):
        out[i] = pr >= np.quantile(hist[-window:], 1 - keep)
        hist.append(pr)
    return out


def evaluate(m1, signals, label):
    p = user_params(strategy="external", sargs=dict(signals={"H1": signals}))
    tr, _, _ = run(m1, p, 1e6, quiet=True)
    return summarize(tr, label)


def summarize(tr, label):
    df = pd.DataFrame(tr)
    df["y"] = pd.to_datetime(df.open_t * 60, unit="s").dt.year
    df = df[df.y >= TEST_YEARS[0]]
    pnl = df.pnl
    eq = pnl.cumsum()
    by = pnl.groupby(df.y).sum().reindex(TEST_YEARS, fill_value=0)
    return dict(label=label, n=len(df), win=(pnl > 0).mean() * 100, pf=pnl[pnl > 0].sum() / -pnl[pnl < 0].sum(),
                net=pnl.sum(), dd=(eq.cummax() - eq).max(), by=by)


def main():
    m1 = pd.read_pickle(sys.argv[1])
    h1 = resample(m1, 60)
    F = h1_features(h1)
    c = h1["close"]
    r2, tr200 = rsi(c, 2), ema(c, 200)
    mode = sys.argv[2] if len(sys.argv) > 2 else "wide"
    if mode == "plan":     # the current plan's own setups: RSI(2) < 10 + daily trend
        from strategies import indicator_filters
        fl, fs = indicator_filters(h1, ["daily_trend"])
        dirs = pd.Series(np.where((c > tr200) & (r2 < 10) & fl, 1, np.where((c < tr200) & (r2 > 90) & fs, -1, 0)),
                         index=h1.index)
    else:
        dirs = pd.Series(np.where((c > tr200) & (r2 < 15), 1, np.where((c < tr200) & (r2 > 85), -1, 0)),
                         index=h1.index)
    dirs.iloc[:800] = 0
    cand = dirs[dirs != 0]
    print(f"candidate set '{mode}': {len(cand)} H1 setups")

    lab = label_candidates(m1, cand)
    X_all = oriented(F.loc[lab.index], lab["dir"].to_numpy())
    y_all = (lab["pnl"] > 0).astype(int).to_numpy()
    years = lab.index.year
    print(f"labelled: {len(lab)}  base win rate {y_all.mean() * 100:.1f}%  avg ${lab.pnl.mean():+.2f}/trade\n")

    picks = {"lgbm": [], "logreg": []}
    imps = []
    aucs = {"lgbm": [], "logreg": []}
    from sklearn.metrics import roc_auc_score
    for Y in TEST_YEARS:
        purge = pd.Timestamp(f"{Y}-01-01")
        close_ts = pd.to_datetime(lab["close_t"] * 60, unit="s")
        tr_mask = (lab.index < purge) & (close_ts < purge).to_numpy()
        te_mask = years == Y
        Xtr, ytr, Xte = X_all[tr_mask], y_all[tr_mask], X_all[te_mask]
        for name, make in (("lgbm", lgbm), ("logreg", logreg)):
            oof = oof_preds(make, Xtr, ytr)
            model = make().fit(Xtr, ytr)
            pr = model.predict_proba(Xte)[:, 1]
            aucs[name].append(roc_auc_score(y_all[te_mask], pr))
            keep_idx = Xte.index[adaptive_keep(oof[~np.isnan(oof)], pr, KEEP)]
            picks[name].append(lab.loc[keep_idx, "dir"])
            if name == "lgbm":
                imps.append(pd.Series(model.booster_.feature_importance("gain"), index=Xtr.columns))
        print(f"test {Y}: trained on {tr_mask.sum()} setups | AUC lgbm {aucs['lgbm'][-1]:.3f}  logreg {aucs['logreg'][-1]:.3f} "
              f"| kept lgbm {len(picks['lgbm'][-1])}/{te_mask.sum()}, logreg {len(picks['logreg'][-1])}/{te_mask.sum()}")

    test_cand = cand[cand.index.year >= TEST_YEARS[0]]
    res = []
    # current hand-made plan
    tr, _, _ = run(m1, user_params(strategy="rsi2", sargs=dict(lo=10, filters=["daily_trend"])), 1e6, quiet=True)
    res.append(summarize(tr, "current plan (RSI2<10 + daily trend)"))
    if mode != "plan":
        res.append(evaluate(m1, test_cand, "all candidates (RSI2<15, no filter)"))
    res.append(evaluate(m1, pd.concat(picks["lgbm"]), f"ML LightGBM keeps {int(KEEP * 100)}%"))
    res.append(evaluate(m1, pd.concat(picks["logreg"]), f"ML logistic keeps {int(KEEP * 100)}%"))
    rnd = []
    rng = np.random.default_rng(1)
    for s in range(20):
        keep = test_cand[rng.random(len(test_cand)) < KEEP]
        rnd.append(evaluate(m1, keep, "random"))
    res.append(dict(label=f"random keeps {int(KEEP * 100)}% (avg of 20)", n=np.mean([r["n"] for r in rnd]),
                    win=np.mean([r["win"] for r in rnd]), pf=np.mean([r["pf"] for r in rnd]),
                    net=np.mean([r["net"] for r in rnd]), dd=np.mean([r["dd"] for r in rnd]),
                    by=sum(r["by"] for r in rnd) / len(rnd)))
    best_rand = max(r["net"] for r in rnd)

    print(f"\nUnseen years 2022-2026, 0.01 lot, $10 SL / $30 TP / EMA5 exit, 24h, raw costs, EA position rules")
    print(f"{'bot':40s} | {'trades':>6s} {'win%':>5s} {'PF':>5s} {'net $':>7s} {'maxDD$':>6s} | " +
          " ".join(f"{y:>6d}" for y in TEST_YEARS))
    for r in res:
        print(f"{r['label']:40s} | {r['n']:6.0f} {r['win']:5.1f} {r['pf']:5.2f} {r['net']:+7.0f} {r['dd']:6.0f} | " +
              " ".join(f"{v:+6.0f}" for v in r["by"]))
    print(f"(best of the 20 random runs: {best_rand:+.0f})")
    print(f"\nmean test AUC (0.5 = coin flip): lgbm {np.mean(aucs['lgbm']):.3f}, logreg {np.mean(aucs['logreg']):.3f}")
    imp = pd.concat(imps, axis=1).mean(axis=1)
    print("top features the model leaned on:", ", ".join(f"{k} ({v / imp.sum() * 100:.0f}%)" for k, v in imp.nlargest(12).items()))


if __name__ == "__main__":
    main()

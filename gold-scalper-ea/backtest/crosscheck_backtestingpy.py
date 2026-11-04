#!/usr/bin/env python3
"""Independent re-implementation of v1.10 in backtesting.py (kernc/backtesting.py, PyPI 'backtesting')
on H1 bars, to cross-check our own engine. Costs: flat $0.13/oz round trip as commission
(= average real raw spread $0.06 + $7/lot commission). Same rules: RSI(2)<10 above EMA200 (mirror for
shorts), SL 2xATR(14), TP 6xATR, exit when close crosses EMA5, 24-bar limit, entries 09-23 server time,
flat on Friday 21:00.

usage: python3 crosscheck_backtestingpy.py xau_m1.pkl
"""
import os
import sys
import warnings

import numpy as np
import pandas as pd
from backtesting import Backtest, Strategy

warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gold_scalper_bt import Params, ema, resample, rsi, run, true_range  # noqa: E402
from strategy_search import MR, tfs  # noqa: E402

SIZE = 10          # ounces per trade (fixed)
COST_SIDE = 0.065  # $ per ounce per side


class RSI2(Strategy):
    def init(self):
        c = pd.Series(self.data.Close)
        h, l = pd.Series(self.data.High), pd.Series(self.data.Low)
        self.r = self.I(lambda: rsi(c, 2).to_numpy(), name="rsi2")
        self.tr = self.I(lambda: ema(c, 200).to_numpy(), name="ema200")
        self.x = self.I(lambda: ema(c, 5).to_numpy(), name="ema5")
        self.atr = self.I(lambda: true_range(h, l, c).rolling(14).mean().to_numpy(), name="atr")
        self.bars_in = 0
        self.risk = {}

    def next(self):
        i = len(self.data) - 1
        if i < 300:
            return
        t = self.data.index[-1] + pd.Timedelta(hours=1)        # next bar open = when orders fill
        c, x = self.data.Close[-1], self.x[-1]
        if self.position:
            self.bars_in += 1
            if (self.position.is_long and c > x) or (self.position.is_short and c < x) or self.bars_in >= 24 \
                    or (t.dayofweek == 4 and t.hour >= 21):
                self.position.close()
            return
        if not (9 <= t.hour < 23) or (t.dayofweek == 4 and t.hour >= 21):
            return
        a = self.atr[-1]
        if not a > 0:
            return
        sl = max(2 * a, 1.0)
        if c > self.tr[-1] and self.r[-1] < 10:
            self.buy(size=SIZE, sl=c - sl, tp=c + 3 * sl)
            self.bars_in = 0
        elif c < self.tr[-1] and self.r[-1] > 90:
            self.sell(size=SIZE, sl=c + sl, tp=c - 3 * sl)
            self.bars_in = 0


def main():
    m1 = pd.read_pickle(sys.argv[1])
    h1 = resample(m1, 60).rename(columns=str.capitalize)
    a = true_range(h1.High, h1.Low, h1.Close).rolling(14).mean()
    out = []
    for label, lo, hi in (("2020-2023", None, "2024-01-01"), ("2024-2026", "2024-01-01", None)):
        sel = h1[(h1.index >= lo) if lo else slice(None)]
        sel = sel[sel.index < hi] if hi else sel
        bt = Backtest(sel, RSI2, cash=1_000_000, commission=lambda size, price: abs(size) * COST_SIDE,
                      exclusive_orders=False, finalize_trades=True)
        st = bt.run()
        tr = st._trades.copy()
        risk = 2 * a.reindex(tr.EntryTime).to_numpy() * SIZE
        risk = np.maximum(risk, 1.0 * SIZE)
        r = (tr.PnL.to_numpy()) / risk
        pf = tr.PnL[tr.PnL > 0].sum() / -tr.PnL[tr.PnL <= 0].sum()
        # our engine, same flat costs (no slippage), fixed size
        d = m1[(m1.index >= lo) if lo else slice(None)]
        d = d[d.index < hi] if hi else d
        ours, _, _ = run(d, Params(strategy="rsi2", sargs=dict(lo=10), **dict(MR, use_tf=tfs("H1"), use_trend=False),
                                   spread=0.06, commission_per_lot=7.0, slippage=0.0, fixed_lots=SIZE / 100,
                                   max_daily_loss_pct=0, max_trades_day=0, max_consec_losses=0), 1e6, quiet=True)
        orr = np.array([t["r"] for t in ours]); op = np.array([t["pnl"] for t in ours])
        out.append(f"{label}: backtesting.py {len(tr)} trades, avgR {np.nanmean(r):+.3f}, PF {pf:.2f}, "
                   f"win {(tr.PnL > 0).mean() * 100:.0f}%  |  our engine {len(orr)} trades, avgR {orr.mean():+.3f}, "
                   f"PF {op[op > 0].sum() / -op[op <= 0].sum():.2f}, win {(op > 0).mean() * 100:.0f}%")
    print("\n".join(out))


if __name__ == "__main__":
    main()

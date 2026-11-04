#!/usr/bin/env python3
"""Combine daily 1-minute XAUUSD CSVs into one pickle with broker-server timestamps.

Source layout: <root>/XAUUSD/1m/YYYY/MM/XAUUSD_1m_YYYY-MM-DD.csv
(e.g. github.com/parshant65-lang/Gold-XAUUSD-1m-2020-2025-Historical-Data)

OANDA MT5 server time = New York time + 7h (UTC+2 in winter, UTC+3 in US summer),
so daily/H4 bars and session hours line up with what MT5 shows.

usage: python3 prepare_data.py <data_root> <out.pkl>
"""
import glob
import os
import sys

import pandas as pd


def main(root, out):
    files = sorted(glob.glob(os.path.join(root, "XAUUSD", "1m", "*", "*", "*.csv")))
    if not files:
        sys.exit(f"no CSVs under {root}")
    frames = [pd.read_csv(f, usecols=["timestamp", "open", "high", "low", "close"]) for f in files]
    df = pd.concat(frames, ignore_index=True).drop_duplicates("timestamp").sort_values("timestamp")
    utc = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    server = utc.dt.tz_convert("America/New_York").dt.tz_localize(None) + pd.Timedelta(hours=7)
    df = df.drop(columns="timestamp")
    df.index = pd.DatetimeIndex(server, name="time")
    df = df[(df["high"] >= df["low"]) & (df["low"] > 0)]
    df.to_pickle(out)
    print(f"{len(files)} files -> {len(df):,} bars, {df.index[0]} .. {df.index[-1]} (server time)")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])

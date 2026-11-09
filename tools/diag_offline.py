# -*- coding: utf-8 -*-
"""离线通道延迟约定诊断：X_offline(t) 对齐 simX(t - lag)。"""
import sys
import pandas as pd
import numpy as np

batch = int(sys.argv[1]) if len(sys.argv) > 1 else 1
sim = pd.read_csv(f"data/processed/sim_batch_{batch:02d}.csv")
v3 = pd.read_csv(f"data/processed/batches/batch_{batch:02d}.csv")
sim["X"] = sim[["A0", "A1", "A3", "A4"]].sum(axis=1)

xoff = v3[["time_h", "X_offline"]].dropna()
print(f"--- batch {batch}: X_offline points ---")
for _, r in xoff.iterrows():
    t = r["time_h"]
    xv = r["X_offline"]
    s_same = sim[sim.time_h <= t].iloc[-1]["X"]
    s_lag08 = sim[sim.time_h <= t - 0.8].iloc[-1]["X"] if (sim.time_h <= t - 0.8).any() else float("nan")
    s_lag4 = sim[sim.time_h <= t - 4].iloc[-1]["X"] if (sim.time_h <= t - 4).any() else float("nan")
    print(f"  t={t:6.1f} Xoff={xv:8.3f}  simX(t)={s_same:8.3f}  simX(t-0.8)={s_lag08:8.3f}  simX(t-4)={s_lag4:8.3f}")

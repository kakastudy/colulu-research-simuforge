# -*- coding: utf-8 -*-
"""sim PAA 细粒度轨迹 + Fpaa 对照。"""
import sys
import pandas as pd
import numpy as np

batch = int(sys.argv[1]) if len(sys.argv) > 1 else 1
sim = pd.read_csv(f"data/processed/sim_batch_{batch:02d}.csv")
v3 = pd.read_csv(f"data/processed/batches/batch_{batch:02d}.csv")

print(f"--- batch {batch}: sim PAA + V3 Fpaa (t=60..110 step 2) ---")
for t in range(60, 112, 2):
    s = sim[sim.time_h <= t].iloc[-1]
    v = v3[v3.time_h <= t].iloc[-1]
    print(f"  t={t:5d}  simPAA={s['PAA']:8.1f}  simP={s['P']:7.3f}  v3Fpaa={v['Fpaa']:6.2f}  v3PAAoff={v['PAA_offline'] if not pd.isna(v['PAA_offline']) else float('nan'):8.1f}")

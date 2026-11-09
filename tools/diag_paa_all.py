# -*- coding: utf-8 -*-
"""V3 PAA_offline 全点 vs sim PAA。"""
import sys
import pandas as pd
import numpy as np

batch = int(sys.argv[1]) if len(sys.argv) > 1 else 1
sim = pd.read_csv(f"data/processed/sim_batch_{batch:02d}.csv")
v3 = pd.read_csv(f"data/processed/batches/batch_{batch:02d}.csv")

print(f"--- batch {batch}: PAA_offline (V3) vs sim PAA ---")
for _, r in v3[["time_h", "PAA_offline"]].dropna().iterrows():
    t = r["time_h"]
    paa_off = r["PAA_offline"]
    s = sim[sim.time_h <= t].iloc[-1]
    s_paa = s["PAA"]
    s_paa_lag = sim[sim.time_h <= t - 0.8].iloc[-1]["PAA"] if (sim.time_h <= t - 0.8).any() else float("nan")
    print(f"  t={t:6.1f}  v3PAAoff={paa_off:8.1f}  simPAA(t)={s_paa:8.1f}  simPAA(t-0.8)={s_paa_lag:8.1f}  Fpaa={r['Fpaa'] if 'Fpaa' in r else float('nan')}")

# -*- coding: utf-8 -*-
"""轨迹诊断：sim vs V3 关键通道逐点对比。"""
import sys
import pandas as pd
import numpy as np

batch = int(sys.argv[1]) if len(sys.argv) > 1 else 1
sim = pd.read_csv(f"data/processed/sim_batch_{batch:02d}.csv")
v3 = pd.read_csv(f"data/processed/batches/batch_{batch:02d}.csv")
sim["X"] = sim[["A0", "A1", "A3", "A4"]].sum(axis=1)

print(f"--- batch {batch}: X (sim) vs X_offline (v3) ---")
for t in [1, 2, 5, 10, 20, 30, 40, 60, 100, 150, 200, 226]:
    s = sim[sim.time_h <= t].iloc[-1]
    v = v3[v3.time_h <= t].iloc[-1]
    xoff = v["X_offline"]
    xoff_s = f"{xoff:8.3f}" if not pd.isna(xoff) else "     NaN"
    print(f"  t={t:6.1f}  simX={s['X']:8.3f}  v3Xoff={xoff_s}  mux={s['mux']:.4f} mup={s['mup']:.4f}")

print("\n--- S fine around t=5-25 ---")
for t in [5, 6, 8, 10, 12, 15, 18, 20, 22, 25]:
    s = sim[sim.time_h <= t].iloc[-1]
    v = v3[v3.time_h <= t].iloc[-1]
    print(f"  t={t:5.1f}  simS={s['S']:8.4f} v3S={v['S']:8.4f}  simX={s['X']:7.3f}")

print("\n--- end of batch (t=210-226) ---")
for t in [210, 215, 218, 220, 222, 224, 226]:
    s = sim[sim.time_h <= t].iloc[-1]
    v = v3[v3.time_h <= t].iloc[-1]
    print(f"  t={t:5.1f}  simS={s['S']:8.4f} v3S={v['S']:8.4f}  simpH={s['pH']:6.3f} v3pH={v['pH']:6.3f}  "
          f"simP={s['P']:7.3f} v3P={v['P']:7.3f}  Fb={v['Fb']:7.2f} Fa={v['Fa']:6.2f} Fremoved={v['Fremoved']:8.1f}")

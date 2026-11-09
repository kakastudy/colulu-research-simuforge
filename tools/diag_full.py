# -*- coding: utf-8 -*-
"""全通道逐点对比 sim vs V3。"""
import sys
import pandas as pd
import numpy as np

batch = int(sys.argv[1]) if len(sys.argv) > 1 else 1
sim = pd.read_csv(f"data/processed/sim_batch_{batch:02d}.csv")
v3 = pd.read_csv(f"data/processed/batches/batch_{batch:02d}.csv")
sim["X"] = sim[["A0", "A1", "A3", "A4"]].sum(axis=1)

channels = ["S", "DO2", "P", "V", "pH", "T", "CO2outgas", "O2", "OUR", "CER", "X", "Fb", "Fc", "Fg"]
print(f"{'t':>7} " + " ".join(f"{c:>9}" for c in channels))
for t in [0.4, 1, 2, 5, 8, 10, 12, 20, 40, 60, 100, 150, 200, 226]:
    s = sim[sim.time_h <= t].iloc[-1]
    v = v3[v3.time_h <= t].iloc[-1]
    row = f"{t:7.1f}"
    for c in channels:
        sv = s.get(c, float("nan"))
        vv = v.get(c, float("nan"))
        if c == "X":
            vv = v["X_offline"]
        row += f" {sv:9.3f}" if not pd.isna(sv) else f" {'nan':>9}"
    print(row)
print()
print("V3 values:")
print(f"{'t':>7} " + " ".join(f"{c:>9}" for c in channels))
for t in [0.4, 1, 2, 5, 8, 10, 12, 20, 40, 60, 100, 150, 200, 226]:
    v = v3[v3.time_h <= t].iloc[-1]
    row = f"{t:7.1f}"
    for c in channels:
        vv = v.get(c, float("nan"))
        if c == "X":
            vv = v["X_offline"]
        row += f" {vv:9.3f}" if not pd.isna(vv) else f" {'nan':>9}"
    print(row)

# -*- coding: utf-8 -*-
"""Batch 23 全批次对照：X_offline 平台期 vs sim CO2d 穿越。"""
import sys, os
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from simulate import simulate_open_loop

d = pd.read_csv("data/processed/batches/batch_23.csv")
params = {"mux": 0.35, "mup": 0.070, "alpha_kla": 85.0,
          "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0,
          "dist_flag": 1, "dist_tcin_asym": 10, "m_s": 0.029}
sim, _ = simulate_open_loop(23, params)
sim_i = sim.set_index("time_h")

print("=== Batch 23: V3 X_offline 全轨迹 (非 NaN) ===")
xo = pd.to_numeric(d["X_offline"], errors="coerce")
print(pd.DataFrame({"t": d["time_h"][xo.notna()], "X_offline": xo.dropna(), "P_offline": pd.to_numeric(d["P_offline"], errors="coerce").dropna().reindex(xo.dropna().index)}).to_string(index=False, float_format=lambda v: f"{v:8.2f}"))

print("\n=== 每 12h 粗采样对照 ===")
for t in range(20, int(d["time_h"].iloc[-1]), 12):
    idx = sim_i.index[np.abs(sim_i.index - t) < 0.11]
    if not len(idx):
        continue
    r_sim = sim_i.loc[idx[0]]
    dv = d.iloc[(d["time_h"] - t).abs().argmin()]
    print(f"t={t:3d}: CO2d_sim={r_sim['CO2d']:5.2f}  P_sim={r_sim['P']:6.2f} P_v3={float(dv['P']):6.2f} P_off={dv['P_offline'] if not pd.isna(dv['P_offline']) else 'NaN':>7} X_off={dv['X_offline'] if not pd.isna(dv['X_offline']) else 'NaN':>6} pH_sim={r_sim['pH']:4.2f} pH_v3={float(dv['pH']):4.2f}")

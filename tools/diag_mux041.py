# -*- coding: utf-8 -*-
"""对比 mux=0.41 (nominal) vs V3 的早期轨迹。"""
import sys
import os
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from simulate import simulate_open_loop, yield_metrics

# mux=0.41 nominal
params = {"mux": 0.41, "mup": 0.041, "alpha_kla": 85.0, "PAA_c": 530000.0,
          "N_conc_paa": 150000.0, "c_oil": 1000.0}
sim, d = simulate_open_loop(1, params)
sim.to_csv("runs/sim_mux041.csv", index=False)

v3 = pd.read_csv("data/processed/batches/batch_01.csv")
m = sim[["time_h","S","P","CO2outgas"]].merge(
    v3[["time_h","S","P","CO2outgas"]], on="time_h", suffixes=("_sim","_v3"))
print(m[["time_h","S_v3","S_sim","P_v3","P_sim","CO2outgas_v3","CO2outgas_sim"]].iloc[::20].to_string())

co2d_max = sim["CO2d"].max()
print(f"\nCO2d max = {co2d_max:.2f} (threshold 7.57)")
print(f"Yield = {yield_metrics(sim, d)['total_sim_g']:,.0f}")

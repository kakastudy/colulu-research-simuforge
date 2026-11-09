# -*- coding: utf-8 -*-
"""检查 x0b 在 mux=0.41 下是否影响早期 S 轨迹。"""
import sys
import os
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from simulate import simulate_open_loop

v3 = pd.read_csv("data/processed/batches/batch_01.csv")
v3_s_early = v3[v3.time_h <= 4.4].iloc[-1]["S"]
print(f"V3 S@4.4 = {v3_s_early:.4f}")
print()

for x0b in [0.30, 0.40, 0.50, 0.60, 0.70]:
    params = {"mux": 0.41, "mup": 0.041, "alpha_kla": 85.0, "PAA_c": 530000.0,
              "N_conc_paa": 150000.0, "c_oil": 1000.0}
    sim, d = simulate_open_loop(1, params, x0_biomass=x0b)
    s_early = sim[sim.time_h <= 4.4].iloc[-1]["S"]
    row0 = sim.iloc[0]
    print(f"x0b={x0b:.2f}: A0@0.2={row0['A0']:.4f} A1@0.2={row0['A1']:.4f} "
          f"X@0.2={row0['A0']+row0['A1']:.4f} S@4.4={s_early:.4f} "
          f"X@200={sim[sim.time_h<=200].iloc[-1]['A0']+sim[sim.time_h<=200].iloc[-1]['A1']:.1f}")

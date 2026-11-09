# -*- coding: utf-8 -*-
"""扫描 mux/mup，找无崩溃区域。"""
import sys
import os
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from simulate import simulate_open_loop, yield_metrics

print("=== mux scan (mup=0.041 fixed) ===")
for mux in [0.20, 0.25, 0.30, 0.35, 0.41, 0.47, 0.53, 0.60]:
    params = {"mux": mux, "mup": 0.041, "alpha_kla": 85.0, "PAA_c": 530000.0,
              "N_conc_paa": 150000.0, "c_oil": 1000.0}
    sim, d = simulate_open_loop(1, params)
    co2d_max = sim["CO2d"].max()
    s_last = sim["S"].iloc[-1]
    p_last = sim["P"].iloc[-1]
    x_last = sim["A0"].iloc[-1] + sim["A1"].iloc[-1]
    co2_last = sim["CO2outgas"].iloc[-1]
    y = yield_metrics(sim, d)["total_sim_g"]
    crashed = "CRASH" if co2d_max > 7.57 else "ok"
    print(f"mux={mux:.2f}: CO2d={co2d_max:.2f} {crashed} S_l={s_last:.4f} P_l={p_last:.2f} X_l={x_last:.2f} CO2_l={co2_last:.2f} yld={y:,.0f}")

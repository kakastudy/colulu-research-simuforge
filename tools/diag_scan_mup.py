# -*- coding: utf-8 -*-
"""扫描 mup，看是否降低 X 并避免崩溃。"""
import sys
import os
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from simulate import simulate_open_loop, yield_metrics

print("=== mup scan (mux=0.24, kla=85) ===")
for mup in [0.041, 0.060, 0.080, 0.100, 0.120, 0.150]:
    params = {"mux": 0.24, "mup": mup, "alpha_kla": 85.0, "PAA_c": 530000.0,
              "N_conc_paa": 150000.0, "c_oil": 1000.0}
    sim, d = simulate_open_loop(1, params)
    co2d_max = sim["CO2d"].max()
    row = sim[sim.time_h <= 200.0].iloc[-1]
    x_pre = row["A0"] + row["A1"]
    p_pre = row["P"]
    co2_pre = row["CO2outgas"]
    s_last = sim["S"].iloc[-1]
    p_last = sim["P"].iloc[-1]
    y = yield_metrics(sim, d)["total_sim_g"]
    crashed = "CRASH" if co2d_max > 7.57 else "ok"
    print(f"mup={mup:.3f}: CO2d={co2d_max:.2f} {crashed} "
          f"X@200={x_pre:.1f} P@200={p_pre:.1f} CO2@200={co2_pre:.2f} "
          f"S_l={s_last:.3f} P_l={p_last:.1f} yld={y:,.0f}")

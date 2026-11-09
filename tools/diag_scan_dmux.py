# -*- coding: utf-8 -*-
"""扫描 distMuX ∈ [-0.15, 0]，看负扰动是否降低 X、提高 P、避免崩溃。"""
import sys
import os
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from simulate import simulate_open_loop, yield_metrics

print("=== distMuX scan (mux=0.41, kla=85, mup=0.041, dist_flag=1) ===")
for dmux in [0.0, -0.02, -0.04, -0.06, -0.08, -0.10, -0.12, -0.15]:
    params = {"mux": 0.41, "mup": 0.041, "alpha_kla": 85.0, "PAA_c": 530000.0,
              "N_conc_paa": 150000.0, "c_oil": 1000.0,
              "dist_flag": 1, "dist_mux": dmux}
    sim, d = simulate_open_loop(1, params)
    co2d_max = sim["CO2d"].max()
    row_early = sim[sim.time_h <= 4.4].iloc[-1]
    s_early = row_early["S"]
    row200 = sim[sim.time_h <= 200.0].iloc[-1]
    x_pre = row200["A0"] + row200["A1"]
    p_pre = row200["P"]
    co2_pre = row200["CO2outgas"]
    do2_pre = row200["DO2"]
    s_last = sim["S"].iloc[-1]
    p_last = sim["P"].iloc[-1]
    y = yield_metrics(sim, d)["total_sim_g"]
    crashed = "CRASH" if co2d_max > 7.57 else "ok"
    print(f"distMuX={dmux:+.2f}: CO2d={co2d_max:.2f} {crashed} S@4.4={s_early:.3f} "
          f"X@200={x_pre:.1f} P@200={p_pre:.1f} DO2@200={do2_pre:.1f} "
          f"CO2@200={co2_pre:.2f} S_l={s_last:.3f} P_l={p_last:.1f} yld={y:,.0f}")

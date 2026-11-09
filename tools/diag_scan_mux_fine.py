# -*- coding: utf-8 -*-
"""精细扫描 mux ∈ [0.24, 0.41]，找早期 S 匹配 + 不崩溃的组合。"""
import sys
import os
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from simulate import simulate_open_loop, yield_metrics

print("=== Fine mux scan (kla=85, mup=0.041) ===")
for mux in [0.25, 0.26, 0.27, 0.28, 0.29, 0.30, 0.31, 0.32, 0.33, 0.34, 0.35, 0.36, 0.37, 0.38, 0.39, 0.40]:
    params = {"mux": mux, "mup": 0.041, "alpha_kla": 85.0, "PAA_c": 530000.0,
              "N_conc_paa": 150000.0, "c_oil": 1000.0}
    sim, d = simulate_open_loop(1, params)
    co2d_max = sim["CO2d"].max()
    # 早期 S 对比 (t=4.4)
    row_early = sim[sim.time_h <= 4.4].iloc[-1]
    s_early = row_early["S"]
    # t=200 附近
    row200 = sim[sim.time_h <= 200.0].iloc[-1]
    x_pre = row200["A0"] + row200["A1"]
    p_pre = row200["P"]
    co2_pre = row200["CO2outgas"]
    s_last = sim["S"].iloc[-1]
    p_last = sim["P"].iloc[-1]
    y = yield_metrics(sim, d)["total_sim_g"]
    crashed = "CRASH" if co2d_max > 7.57 else "ok"
    print(f"mux={mux:.2f}: CO2d={co2d_max:.2f} {crashed} S@4.4={s_early:.3f} "
          f"X@200={x_pre:.1f} P@200={p_pre:.1f} CO2@200={co2_pre:.2f} "
          f"S_l={s_last:.3f} P_l={p_last:.1f} yld={y:,.0f}")

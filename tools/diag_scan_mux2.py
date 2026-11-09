# -*- coding: utf-8 -*-
"""细扫 mux 0.20-0.26，看预崩溃 X 和 CO2d。"""
import sys
import os
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from simulate import simulate_open_loop, yield_metrics

for mux in [0.20, 0.21, 0.22, 0.23, 0.24, 0.25, 0.26]:
    params = {"mux": mux, "mup": 0.041, "alpha_kla": 85.0, "PAA_c": 530000.0,
              "N_conc_paa": 150000.0, "c_oil": 1000.0}
    sim, d = simulate_open_loop(1, params)
    co2d_max = sim["CO2d"].max()
    # 预崩溃 X (t=200.0)
    row = sim[sim.time_h <= 200.0].iloc[-1]
    x_pre = row["A0"] + row["A1"]
    s_pre = row["S"]
    co2_pre = row["CO2outgas"]
    s_last = sim["S"].iloc[-1]
    p_last = sim["P"].iloc[-1]
    y = yield_metrics(sim, d)["total_sim_g"]
    crashed = "CRASH" if co2d_max > 7.57 else "ok"
    print(f"mux={mux:.2f}: CO2d={co2d_max:.2f} {crashed} X@200={x_pre:.1f} S@200={s_pre:.4f} "
          f"CO2@200={co2_pre:.2f} S_l={s_last:.2f} P_l={p_last:.2f} yld={y:,.0f}")

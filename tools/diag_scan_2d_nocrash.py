# -*- coding: utf-8 -*-
"""2D scan in no-crash zone: kla x mux，找 X~24 且 P~29。"""
import sys
import os
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from simulate import simulate_open_loop, yield_metrics

print("=== 2D scan: kla x mux (mup=0.041) ===")
for kla in [55.0, 58.0, 60.0, 62.0]:
    for mux in [0.30, 0.35, 0.41, 0.50, 0.60]:
        params = {"mux": mux, "mup": 0.041, "alpha_kla": kla, "PAA_c": 530000.0,
                  "N_conc_paa": 150000.0, "c_oil": 1000.0}
        sim, d = simulate_open_loop(1, params)
        co2d_max = sim["CO2d"].max()
        row200 = sim[sim.time_h <= 200.0].iloc[-1]
        x_pre = row200["A0"] + row200["A1"]
        p_pre = row200["P"]
        co2_pre = row200["CO2outgas"]
        s_last = sim["S"].iloc[-1]
        p_last = sim["P"].iloc[-1]
        y = yield_metrics(sim, d)["total_sim_g"]
        crashed = "CRASH" if co2d_max > 7.57 else "ok"
        print(f"kla={kla:.0f} mux={mux:.2f}: CO2d={co2d_max:.2f} {crashed} "
              f"X@200={x_pre:.1f} P@200={p_pre:.1f} CO2@200={co2_pre:.2f} "
              f"S_l={s_last:.3f} P_l={p_last:.1f} yld={y:,.0f}")

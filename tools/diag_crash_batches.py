# -*- coding: utf-8 -*-
"""检查多个批次是否发生 CO2d 崩溃（nominal params）。"""
import sys
import os
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from simulate import simulate_open_loop, yield_metrics
from params import make_params

params = {"mux": 0.41, "mup": 0.041, "alpha_kla": 85.0, "PAA_c": 530000.0,
          "N_conc_paa": 150000.0, "c_oil": 1000.0}

for b in [1, 8, 11, 16, 22]:
    sim, d = simulate_open_loop(b, params)
    co2d_max = sim["CO2d"].max()
    s_last = sim["S"].iloc[-1]
    p_last = sim["P"].iloc[-1]
    y = yield_metrics(sim, d)["total_sim_g"]
    print(f"batch {b:3d}: CO2d_max={co2d_max:.2f} S_last={s_last:.4f} P_last={p_last:.2f} yield={y:,.0f}")

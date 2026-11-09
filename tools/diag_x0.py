# -*- coding: utf-8 -*-
"""测试初始生物量 x0 对崩溃和 X 的影响。"""
import sys
import os
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from simulate import simulate_open_loop, yield_metrics, build_initial_state, load_batch
from params import make_params

# 临时修改 build_initial_state 的 x0_biomass
import simulate as sim_mod

for x0 in [0.3, 0.4, 0.5, 0.6, 0.7]:
    orig = sim_mod.build_initial_state
    def make_bs(x0v):
        def bs(d, x0_biomass=x0v, paa0=1400.0, nh30=1700.0):
            return orig(d, x0_biomass=x0v, paa0=paa0, nh30=nh30)
        return bs
    sim_mod.build_initial_state = make_bs(x0)
    params = {"mux": 0.41, "mup": 0.041, "alpha_kla": 85.0, "PAA_c": 530000.0,
              "N_conc_paa": 150000.0, "c_oil": 1000.0}
    sim, d = sim_mod.simulate_open_loop(1, params)
    co2d_max = sim["CO2d"].max()
    s_last = sim["S"].iloc[-1]
    p_last = sim["P"].iloc[-1]
    x_last = sim["A0"].iloc[-1] + sim["A1"].iloc[-1]
    y = yield_metrics(sim, d)["total_sim_g"]
    crashed = "CRASH" if co2d_max > 7.57 else "ok"
    print(f"x0={x0}: CO2d_max={co2d_max:.2f} {crashed} S_last={s_last:.4f} P_last={p_last:.2f} X_last={x_last:.2f} yield={y:,.0f}")
    sim_mod.build_initial_state = orig

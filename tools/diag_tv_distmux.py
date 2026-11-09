# -*- coding: utf-8 -*-
"""Test time-varying distMuX: scan distMuX_asym to match V3 X trajectory.

Key: distMuX(t) = asym * (1 - exp(-t/40)) starts at 0 (early batch mux=0.41)
and gradually reduces mux_max in late batch → X peaks lower and declines.
"""
import sys, os
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from simulate import simulate_open_loop, yield_metrics

d = pd.read_csv("data/processed/batches/batch_01.csv")
xoff_mask = pd.to_numeric(d["X_offline"], errors="coerce").notna()
v3_x = d.loc[xoff_mask, "X_offline"].to_numpy(float)
v3_t = d.loc[xoff_mask, "time_h"].to_numpy(float)

print("=== Time-varying distMuX scan (batch 1) ===")
print(f"V3 X: peak={v3_x.max():.1f}@t={v3_t[v3_x.argmax()]:.0f}, end={v3_x[-1]:.1f}")
print()

for dmux_asym in [0.0, -0.02, -0.04, -0.06, -0.08, -0.10, -0.12, -0.15, -0.18]:
    params = {
        "mux": 0.41, "alpha_kla": 85.0, "mup": 0.041,
        "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0,
        "dist_flag": 1, "dist_mux_asym": dmux_asym,
    }
    sim, _ = simulate_open_loop(1, params)
    sim_x = (sim["A0"] + sim["A1"]).to_numpy(float)
    sim_t = sim["time_h"].to_numpy(float)
    sim_x_interp = np.interp(v3_t, sim_t, sim_x)
    rmse = np.sqrt(np.mean((sim_x_interp - v3_x) ** 2))

    x4 = np.interp(4.4, sim_t, sim_x)
    x100 = np.interp(100.4, sim_t, sim_x)
    x156 = np.interp(156.4, sim_t, sim_x)
    x196 = np.interp(196.4, sim_t, sim_x)
    co2d_max = sim["CO2d"].max()
    crashed = co2d_max > 7.57

    ym = yield_metrics(sim, d)
    print(f"dMuX={dmux_asym:+.2f}: RMSE={rmse:.2f} {'CRASH' if crashed else 'ok'} "
          f"X@4={x4:.2f} X@100={x100:.1f} X@156={x156:.1f} X@196={x196:.1f} "
          f"CO2d={co2d_max:.2f} yield={ym['rel_err_total']:+.1%}")

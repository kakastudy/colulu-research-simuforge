# -*- coding: utf-8 -*-
"""Scan time-varying distTcin: Tcin shift affects T_inhib → mu_e → growth."""
import sys, os
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from simulate import simulate_open_loop, yield_metrics

d = pd.read_csv("data/processed/batches/batch_01.csv")
xoff_mask = pd.to_numeric(d["X_offline"], errors="coerce").notna()
v3_x = d.loc[xoff_mask, "X_offline"].to_numpy(float)
v3_t = d.loc[xoff_mask, "time_h"].to_numpy(float)

print("=== Time-varying distTcin scan (batch 1) ===")
print(f"V3 X: peak={v3_x.max():.1f}@t={v3_t[v3_x.argmax()]:.0f}, end={v3_x[-1]:.1f}")
print()

for dtcin_asym in [0, -2, -4, -6, -8, -10, -15, -20]:
    params = {
        "mux": 0.41, "alpha_kla": 85.0, "mup": 0.041,
        "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0,
        "dist_flag": 1, "dist_tcin_asym": dtcin_asym,
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
    T_max = sim["T"].max()

    ym = yield_metrics(sim, d)
    print(f"dTcin={dtcin_asym:+.0f}: RMSE={rmse:.2f} {'CRASH' if crashed else 'ok'} "
          f"X@4={x4:.2f} X@100={x100:.1f} X@156={x156:.1f} X@196={x196:.1f} "
          f"CO2d={co2d_max:.2f} T_max={T_max:.1f} yield={ym['rel_err_total']:+.1%}")

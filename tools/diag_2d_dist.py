# -*- coding: utf-8 -*-
"""2D scan: distMuX_asym × distTcin_asym (time-varying)."""
import sys, os
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from simulate import simulate_open_loop, yield_metrics

d = pd.read_csv("data/processed/batches/batch_01.csv")
xoff_mask = pd.to_numeric(d["X_offline"], errors="coerce").notna()
v3_x = d.loc[xoff_mask, "X_offline"].to_numpy(float)
v3_t = d.loc[xoff_mask, "time_h"].to_numpy(float)

print("=== 2D scan: distMuX × distTcin (batch 1) ===")
print(f"{'dMuX':>6s} {'dTcin':>6s} {'RMSE':>6s} {'CO2d':>6s} {'X@156':>6s} {'yield':>7s} {'status':>6s}")

best_rmse = 1e9
best_params = None

for dmux in [0.0, -0.05, -0.10, -0.15]:
    for dtcin in [0, -5, -10, -15, -20]:
        params = {
            "mux": 0.41, "alpha_kla": 85.0, "mup": 0.041,
            "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0,
            "dist_flag": 1,
            "dist_mux_asym": dmux, "dist_tcin_asym": dtcin,
        }
        sim, _ = simulate_open_loop(1, params)
        sim_x = (sim["A0"] + sim["A1"]).to_numpy(float)
        sim_t = sim["time_h"].to_numpy(float)
        sim_x_interp = np.interp(v3_t, sim_t, sim_x)
        rmse = np.sqrt(np.mean((sim_x_interp - v3_x) ** 2))

        x156 = np.interp(156.4, sim_t, sim_x)
        co2d_max = sim["CO2d"].max()
        crashed = co2d_max > 7.57
        ym = yield_metrics(sim, d)
        status = "CRASH" if crashed else "ok"

        print(f"{dmux:>+6.2f} {dtcin:>+6d} {rmse:>6.2f} {co2d_max:>6.2f} {x156:>6.1f} "
              f"{ym['rel_err_total']:>+6.1%} {status:>6s}", flush=True)

        if not crashed and rmse < best_rmse:
            best_rmse = rmse
            best_params = (dmux, dtcin)

print(f"\nBest no-crash: dMuX={best_params[0]:+.2f} dTcin={best_params[1]:+d} RMSE={best_rmse:.2f}")

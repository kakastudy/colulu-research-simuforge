# -*- coding: utf-8 -*-
"""Grid search: mux × x0_biomass, targeting V3 X_offline RMSE.

Key insight: sim X is LOWER at t=4.4 but HIGHER at t=12.4+ vs V3.
Higher x0b → higher early X (matches t=4.4) but higher mid X (diverges from t=12.4).
Higher mux → higher growth rate → higher mid X.
Need to find combo where early X matches AND mid X doesn't overshoot.
"""
import sys
import os
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from simulate import simulate_open_loop

d = pd.read_csv("data/processed/batches/batch_01.csv")
xoff_mask = pd.to_numeric(d["X_offline"], errors="coerce").notna()
v3_x = d.loc[xoff_mask, "X_offline"].to_numpy(float)
v3_t = d.loc[xoff_mask, "time_h"].to_numpy(float)

print("=== Grid search: mux × x0b ===")
print(f"V3 X_offline: {len(v3_x)} points, peak={v3_x.max():.1f}@t={v3_t[v3_x.argmax()]:.0f}")
print()

best_rmse = 1e9
best_params = None

for mux in [0.35, 0.38, 0.41, 0.44, 0.47]:
    for x0b in [0.50, 0.60, 0.70, 0.80, 0.90]:
        params = {
            "mux": mux, "alpha_kla": 85.0, "mup": 0.041,
            "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0,
            "x0_biomass": x0b, "x0_force": True,
        }
        sim, _ = simulate_open_loop(1, params)
        sim_x = (sim["A0"] + sim["A1"]).to_numpy(float)
        sim_t = sim["time_h"].to_numpy(float)
        sim_x_interp = np.interp(v3_t, sim_t, sim_x)
        rmse = np.sqrt(np.mean((sim_x_interp - v3_x) ** 2))
        co2d_max = sim["CO2d"].max()
        crashed = "CRASH" if co2d_max > 7.57 else "ok"

        # Print key metrics
        x4 = np.interp(4.4, sim_t, sim_x)
        x12 = np.interp(12.4, sim_t, sim_x)
        x100 = np.interp(100.4, sim_t, sim_x)
        x156 = np.interp(156.4, sim_t, sim_x)

        print(f"mux={mux:.2f} x0b={x0b:.2f}: RMSE={rmse:.2f} {crashed} "
              f"X@4.4={x4:.2f} X@12.4={x12:.2f} X@100={x100:.1f} X@156={x156:.1f}")

        if rmse < best_rmse:
            best_rmse = rmse
            best_params = (mux, x0b)

print(f"\nBest: mux={best_params[0]:.2f} x0b={best_params[1]:.2f} RMSE={best_rmse:.2f}")

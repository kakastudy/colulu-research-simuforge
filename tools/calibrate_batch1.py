# -*- coding: utf-8 -*-
"""Per-batch calibration: optimize mux, alpha_kla, x0_biomass against V3 X_offline.

Objective: minimize RMSE of (sim.X - V3.X_offline) at X_offline time points.
Uses scipy.optimize.minimize (Nelder-Mead, no gradient).
"""
import sys
import os
import time
import numpy as np
import pandas as pd
from scipy.optimize import minimize

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from simulate import simulate_open_loop

# Load V3 X_offline
d = pd.read_csv("data/processed/batches/batch_01.csv")
xoff_mask = pd.to_numeric(d["X_offline"], errors="coerce").notna()
v3_x = d.loc[xoff_mask, "X_offline"].to_numpy(float)
v3_t = d.loc[xoff_mask, "time_h"].to_numpy(float)


def objective(params_arr):
    mux, kla, x0b = params_arr
    params = {
        "mux": float(mux),
        "alpha_kla": float(kla),
        "mup": 0.041,
        "PAA_c": 530000.0,
        "N_conc_paa": 150000.0,
        "c_oil": 1000.0,
        "x0_biomass": float(x0b),
        "x0_force": True,
    }
    sim, _ = simulate_open_loop(1, params)
    # Interpolate sim X at V3 X_offline time points
    sim_x = (sim["A0"] + sim["A1"]).to_numpy(float)
    sim_t = sim["time_h"].to_numpy(float)
    # Linear interpolation
    sim_x_interp = np.interp(v3_t, sim_t, sim_x)
    rmse = np.sqrt(np.mean((sim_x_interp - v3_x) ** 2))
    # Penalty for crash
    co2d_max = sim["CO2d"].max()
    crash_penalty = max(0.0, (co2d_max - 7.57)) ** 2 * 10.0
    return rmse + crash_penalty


print("=== Per-batch calibration (batch 1) ===")
print(f"V3 X_offline: {len(v3_x)} points, range {v3_x.min():.1f}-{v3_x.max():.1f}")

# Initial guess
x0 = [0.41, 85.0, 0.528]
result = minimize(objective, x0, method="Nelder-Mead",
                  options={"maxiter": 30, "xatol": 0.01, "fatol": 0.01, "disp": True})

mux_opt, kla_opt, x0b_opt = result.x
print(f"\nOptimal: mux={mux_opt:.3f} kla={kla_opt:.1f} x0b={x0b_opt:.3f}")
print(f"Objective: {result.fun:.4f}")

# Verify with optimal params
params = {
    "mux": float(mux_opt),
    "alpha_kla": float(kla_opt),
    "mup": 0.041,
    "PAA_c": 530000.0,
    "N_conc_paa": 150000.0,
    "c_oil": 1000.0,
    "x0_biomass": float(x0b_opt),
    "x0_force": True,
}
sim, _ = simulate_open_loop(1, params)

print("\n=== Comparison ===")
for t in [4.4, 12.4, 24.4, 48.4, 100.4, 156.4, 196.4, 200.4]:
    si = sim[sim.time_h <= t].iloc[-1]
    x = si["A0"] + si["A1"]
    co2d = si["CO2d"]
    p = si["P"]
    print(f"t={t}: X={x:.2f} CO2d={co2d:.2f} P={p:.1f}")

co2d_max = sim["CO2d"].max()
print(f"\nCO2d_max={co2d_max:.2f} {'CRASH' if co2d_max > 7.57 else 'ok'}")

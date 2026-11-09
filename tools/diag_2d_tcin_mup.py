# -*- coding: utf-8 -*-
"""2D scan: distTcin_asym × mup — dTcin brings X down, mup brings P up."""
import sys, os
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from simulate import simulate_open_loop, yield_metrics

d = pd.read_csv("data/processed/batches/batch_01.csv")
xoff_mask = pd.to_numeric(d["X_offline"], errors="coerce").notna()
v3_x = d.loc[xoff_mask, "X_offline"].to_numpy(float)
v3_t = d.loc[xoff_mask, "time_h"].to_numpy(float)

print("=== 2D scan: distTcin x mup (batch 1) ===")
print(f"{'dTcin':>6s} {'mup':>6s} {'RMSE':>6s} {'CO2d':>6s} {'X@156':>6s} {'yield':>7s} {'status':>6s}")

best = None
for dtcin in [0, -5, -8, -10, -12]:
    for mup in [0.041, 0.050, 0.060, 0.070]:
        params = {
            "mux": 0.41, "alpha_kla": 85.0, "mup": mup,
            "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0,
            "dist_flag": 1, "dist_tcin_asym": dtcin,
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

        print(f"{dtcin:>+6d} {mup:>6.3f} {rmse:>6.2f} {co2d_max:>6.2f} {x156:>6.1f} "
              f"{ym['rel_err_total']:>+6.1%} {status:>6s}", flush=True)

        if not crashed:
            if best is None or (abs(ym['rel_err_total']) < abs(best[4])):
                best = (dtcin, mup, rmse, co2d_max, ym['rel_err_total'])

if best:
    print(f"\nBest no-crash: dTcin={best[0]} mup={best[1]:.3f} RMSE={best[2]:.2f} CO2d={best[3]:.2f} yield={best[4]:+.1%}")
else:
    print("\nNo no-crash combination found.")

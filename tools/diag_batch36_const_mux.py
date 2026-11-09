# -*- coding: utf-8 -*-
"""Batch 36: try constant distMuX (dist_flag=0) to reduce mux_max from start.

The reverse problem: sim S=0.001 (fully consumed) while V3 S=32 (accumulated).
Constant negative distMuX reduces mux_max throughout, slowing growth and
allowing S to accumulate (matching V3).
"""
import sys, os
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from simulate import simulate_open_loop, yield_metrics

d = pd.read_csv("data/processed/batches/batch_36.csv")
xoff_mask = pd.to_numeric(d["X_offline"], errors="coerce").notna()
v3_x = d.loc[xoff_mask, "X_offline"].to_numpy(float)
v3_t = d.loc[xoff_mask, "time_h"].to_numpy(float)

print("=== Batch 36: constant distMuX scan (dist_flag=0) ===")
print(f"V3 X: peak={v3_x.max():.1f}, end={v3_x[-1]:.1f}")
print(f"V3 S at t=156: {d[d.time_h <= 156.4].iloc[-1]['S']:.3f}, t=200: {d[d.time_h <= 200.4].iloc[-1]['S']:.3f}")
print()

for mux_base in [0.41, 0.35, 0.30]:
    for dmux in [0.0, -0.05, -0.10, -0.15, -0.20, -0.25, -0.30]:
        mux_eff = mux_base + dmux
        if mux_eff < 0.20:
            continue
        params = {
            "mux": mux_base, "alpha_kla": 85.0, "mup": 0.041,
            "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0,
            "dist_flag": 0, "dist_mux_asym": dmux,  # constant (not time-varying)
        }
        sim, _ = simulate_open_loop(36, params)
        sim_x = (sim["A0"] + sim["A1"]).to_numpy(float)
        sim_t = sim["time_h"].to_numpy(float)
        sim_x_interp = np.interp(v3_t, sim_t, sim_x)
        rmse = np.sqrt(np.mean((sim_x_interp - v3_x) ** 2))

        x100 = np.interp(100.4, sim_t, sim_x)
        x156 = np.interp(156.4, sim_t, sim_x)
        s156 = sim[sim.time_h <= 156.4].iloc[-1]["S"]
        s200 = sim[sim.time_h <= 200.4].iloc[-1]["S"]
        p200 = sim[sim.time_h <= 200.4].iloc[-1]["P"]
        co2d_max = sim["CO2d"].max()
        crashed = co2d_max > 7.57

        ym = yield_metrics(sim, d)
        print(f"mux={mux_eff:.2f}: RMSE={rmse:.2f} {'CRASH' if crashed else 'ok'} "
              f"X@100={x100:.1f} X@156={x156:.1f} S@156={s156:.3f} S@200={s200:.3f} "
              f"P@200={p200:.1f} CO2d={co2d_max:.2f} yield={ym['rel_err_total']:+.1%}")

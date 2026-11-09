# -*- coding: utf-8 -*-
"""1D scan: alpha_kla with dTcin=-10, mup=0.060 fixed. Lower kla reduces CO2 transfer."""
import sys, os
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from simulate import simulate_open_loop, yield_metrics

d = pd.read_csv("data/processed/batches/batch_01.csv")

print("=== 1D alpha_kla scan (dTcin=-10, mup=0.060) ===")
print(f"{'kla':>6s} {'RMSE':>6s} {'CO2d':>6s} {'X@156':>6s} {'yield':>7s} {'status':>6s}")

for kla in [30, 40, 50, 60, 70, 85]:
    params = {
        "mux": 0.41, "alpha_kla": kla, "mup": 0.060,
        "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0,
        "dist_flag": 1, "dist_tcin_asym": -10,
    }
    sim, _ = simulate_open_loop(1, params)
    sim_x = (sim["A0"] + sim["A1"]).to_numpy(float)
    sim_t = sim["time_h"].to_numpy(float)
    x156 = np.interp(156.4, sim_t, sim_x)
    co2d_max = sim["CO2d"].max()
    crashed = co2d_max > 7.57
    ym = yield_metrics(sim, d)
    status = "CRASH" if crashed else "ok"
    print(f"{kla:>6.0f} {co2d_max:>6.2f} {x156:>6.1f} {ym['rel_err_total']:>+6.1%} {status:>6s}", flush=True)

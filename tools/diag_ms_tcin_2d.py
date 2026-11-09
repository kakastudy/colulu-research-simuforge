# -*- coding: utf-8 -*-
"""2D scan m_s × distTcin for batches 60 and 92 (crash + yield)."""
import sys, os
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from simulate import simulate_open_loop, yield_metrics

BATCHES = [60, 92]
M_S_GRID = [0.029, 0.015, 0.010, 0.008, 0.005]
TCIN_GRID = [10, 15, 20, 25, 30]

for b in BATCHES:
    d = pd.read_csv(f"data/processed/batches/batch_{b:02d}.csv")
    print(f"\n=== Batch {b} ===", flush=True)
    print(f"{'m_s':>8s} {'dTcin':>6s} {'yield':>8s} {'CO2d':>6s} {'status':>6s} {'S@156':>8s} {'P@200':>8s}", flush=True)
    for m_s in M_S_GRID:
        for dtcin in TCIN_GRID:
            params = {"mux": 0.47, "mup": 0.041, "alpha_kla": 85.0,
                      "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0,
                      "dist_flag": 1, "dist_tcin_asym": dtcin, "m_s": m_s}
            sim, _ = simulate_open_loop(b, params)
            ym = yield_metrics(sim, d)
            co2d_max = sim["CO2d"].max()
            crashed = co2d_max > 7.57
            s156 = sim[sim.time_h <= 156.4].iloc[-1]["S"] if len(sim[sim.time_h <= 156.4]) > 0 else 0.0
            p200 = sim[sim.time_h <= 200.4].iloc[-1]["P"] if len(sim[sim.time_h <= 200.4]) > 0 else 0.0
            status = "CRASH" if crashed else "ok"
            print(f"{m_s:>8.4f} {dtcin:>+6d} {ym['rel_err_total']:>+8.1%} {co2d_max:>6.2f} {status:>6s} "
                  f"{s156:>8.3f} {p200:>8.1f}", flush=True)

# -*- coding: utf-8 -*-
"""Scan m_s for yield-error batches (16, 22, 55, 80) + batch 23."""
import sys, os
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from simulate import simulate_open_loop, yield_metrics

BATCHES = [16, 22, 55, 80, 23]
M_S_GRID = [0.029, 0.025, 0.020, 0.015, 0.012, 0.010]

for b in BATCHES:
    d = pd.read_csv(f"data/processed/batches/batch_{b:02d}.csv")
    print(f"\n=== Batch {b} ===", flush=True)
    for m_s in M_S_GRID:
        params = {"mux": 0.47, "mup": 0.041, "alpha_kla": 85.0,
                  "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0,
                  "dist_flag": 1, "dist_tcin_asym": 10, "m_s": m_s}
        sim, _ = simulate_open_loop(b, params)
        ym = yield_metrics(sim, d)
        co2d_max = sim["CO2d"].max()
        crashed = co2d_max > 7.57
        status = "CRASH" if crashed else "ok"
        print(f"  m_s={m_s:.4f}: yield={ym['rel_err_total']:+.1%} CO2d={co2d_max:.2f} {status}", flush=True)

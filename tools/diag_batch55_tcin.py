# -*- coding: utf-8 -*-
"""Batch 55: try stronger distTcin to prevent crash at m_s=0.029."""
import sys, os
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from simulate import simulate_open_loop, yield_metrics

d = pd.read_csv("data/processed/batches/batch_55.csv")

print("=== Batch 55: m_s=0.029, mux=0.47, mup=0.041, dTcin scan ===")
for dtcin in [10, 12, 15, 18, 20, 22, 25]:
    params = {"mux": 0.47, "mup": 0.041, "alpha_kla": 85.0,
              "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0,
              "dist_flag": 1, "dist_tcin_asym": dtcin, "m_s": 0.029}
    sim, _ = simulate_open_loop(55, params)
    ym = yield_metrics(sim, d)
    co2d_max = sim["CO2d"].max()
    crashed = co2d_max > 7.57
    status = "CRASH" if crashed else "ok"
    print(f"  dTcin={dtcin:+d}: yield={ym['rel_err_total']:+.1%} CO2d={co2d_max:.2f} {status}", flush=True)

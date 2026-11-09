# -*- coding: utf-8 -*-
"""Verify yield errors with soft-sensing estimated params."""
import sys, os
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from simulate import simulate_open_loop, yield_metrics

# Soft-sensing estimated params
ESTIMATED = {
    8:  {"mux": 0.35, "mup": 0.050, "m_s": 0.025, "dtcin": 15},
    11: {"mux": 0.41, "mup": 0.050, "m_s": 0.025, "dtcin": 15},
}

for b, cp in ESTIMATED.items():
    v3 = pd.read_csv(f"data/processed/batches/batch_{b:02d}.csv")
    params = {"mux": cp["mux"], "mup": cp["mup"], "alpha_kla": 85.0,
              "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0,
              "dist_flag": 1, "dist_tcin_asym": cp["dtcin"], "m_s": cp["m_s"]}
    sim, _ = simulate_open_loop(b, params)
    ym = yield_metrics(sim, v3)
    co2d_max = sim["CO2d"].max()
    print(f"Batch {b}: yield={ym['rel_err_total']:+.1%} CO2d={co2d_max:.2f} {'CRASH' if co2d_max > 7.57 else 'ok'}")

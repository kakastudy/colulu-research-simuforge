# -*- coding: utf-8 -*-
"""Batch 91: scan mux to find zero-yield crossing (between 0.35 and 0.41)."""
import sys, os
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from simulate import simulate_open_loop, yield_metrics

d = pd.read_csv("data/processed/batches/batch_91.csv")

print("=== Batch 91: mux scan (m_s=0.029, mup=0.041, dTcin=0) ===", flush=True)
MUX_GRID = [0.35, 0.36, 0.37, 0.38, 0.39, 0.40, 0.41, 0.42, 0.43]

best_no_crash = None
for mux in MUX_GRID:
    params = {"mux": mux, "mup": 0.041, "alpha_kla": 85.0,
              "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0,
              "dist_flag": 1, "dist_tcin_asym": 0, "m_s": 0.029}
    sim, _ = simulate_open_loop(91, params)
    ym = yield_metrics(sim, d)
    err = ym["rel_err_total"]
    co2d_max = sim["CO2d"].max()
    crashed = co2d_max > 7.57
    status = "CRASH" if crashed else "ok"
    if not crashed:
        if best_no_crash is None or abs(err) < abs(best_no_crash["err"]):
            best_no_crash = {"err": err, "mux": mux, "co2d": co2d_max}
    print(f"  mux={mux:.2f}: yield={err:+.1%} CO2d={co2d_max:.2f} {status}", flush=True)

if best_no_crash:
    print(f"\n  Best no-crash: mux={best_no_crash['mux']:.2f} yield={best_no_crash['err']:+.1%} CO2d={best_no_crash['co2d']:.2f}", flush=True)

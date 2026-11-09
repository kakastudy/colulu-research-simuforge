# -*- coding: utf-8 -*-
"""Batch 92: scan m_s x distO_2in (negative = reduce O2 = reduce growth + CO2)."""
import sys, os
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from simulate import simulate_open_loop, yield_metrics

d = pd.read_csv("data/processed/batches/batch_92.csv")

print("=== Batch 92: m_s x distO_2in scan (mux=0.47, mup=0.041, dTcin=+10) ===", flush=True)
M_S_GRID = [0.020, 0.015, 0.012, 0.010, 0.008]
O2IN_GRID = [-0.01, -0.005, 0.0, 0.005, 0.01, 0.02]

best_no_crash = None
for m_s in M_S_GRID:
    for o2in in O2IN_GRID:
        params = {"mux": 0.47, "mup": 0.041, "alpha_kla": 85.0,
                  "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0,
                  "dist_flag": 1, "dist_tcin_asym": 10, "m_s": m_s,
                  "dist_o2in": o2in}
        sim, _ = simulate_open_loop(92, params)
        ym = yield_metrics(sim, d)
        err = ym["rel_err_total"]
        co2d_max = sim["CO2d"].max()
        crashed = co2d_max > 7.57
        status = "CRASH" if crashed else "ok"
        if not crashed:
            if best_no_crash is None or abs(err) < abs(best_no_crash["err"]):
                best_no_crash = {"err": err, "m_s": m_s, "o2in": o2in, "co2d": co2d_max}
        print(f"  m_s={m_s:.4f} O2in={o2in:+.3f}: yield={err:+.1%} CO2d={co2d_max:.2f} {status}", flush=True)

if best_no_crash:
    print(f"\n  Best no-crash: m_s={best_no_crash['m_s']:.4f} O2in={best_no_crash['o2in']:+.3f} "
          f"yield={best_no_crash['err']:+.1%} CO2d={best_no_crash['co2d']:.2f}", flush=True)

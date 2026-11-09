# -*- coding: utf-8 -*-
"""2D scan m_s x mup for batches 27 (overproduction) and 91 (underproduction)."""
import sys, os
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from simulate import simulate_open_loop, yield_metrics

BATCHES = [27, 91]
M_S_GRID = [0.029, 0.025, 0.020, 0.015, 0.012, 0.010]
MUP_GRID = [0.041, 0.030, 0.020, 0.010]

for b in BATCHES:
    d = pd.read_csv(f"data/processed/batches/batch_{b:02d}.csv")
    print(f"\n=== Batch {b}: m_s x mup scan (mux=0.35, dTcin=+10) ===", flush=True)
    best_no_crash = None
    for m_s in M_S_GRID:
        for mup in MUP_GRID:
            params = {"mux": 0.35, "mup": mup, "alpha_kla": 85.0,
                      "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0,
                      "dist_flag": 1, "dist_tcin_asym": 10, "m_s": m_s}
            sim, _ = simulate_open_loop(b, params)
            ym = yield_metrics(sim, d)
            err = ym["rel_err_total"]
            co2d_max = sim["CO2d"].max()
            crashed = co2d_max > 7.57
            if not crashed:
                if best_no_crash is None or abs(err) < abs(best_no_crash["err"]):
                    best_no_crash = {"err": err, "m_s": m_s, "mup": mup, "co2d": co2d_max}
            status = "CRASH" if crashed else "ok"
            print(f"  m_s={m_s:.4f} mup={mup:.4f}: yield={err:+.1%} CO2d={co2d_max:.2f} {status}", flush=True)
    if best_no_crash:
        print(f"  Best no-crash: m_s={best_no_crash['m_s']:.4f} mup={best_no_crash['mup']:.4f} "
              f"yield={best_no_crash['err']:+.1%}", flush=True)

# -*- coding: utf-8 -*-
"""Scan m_s x dTcin for batches 22 and 80 to find improved no-crash params."""
import sys, os
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from simulate import simulate_open_loop, yield_metrics

BATCHES = {
    22: {"mux": 0.41, "mup": 0.070, "base_m_s": 0.029},
    80: {"mux": 0.35, "mup": 0.041, "base_m_s": 0.025},
}

M_S_GRID = [0.029, 0.025, 0.022, 0.020, 0.018, 0.015]
TCIN_GRID = [10, 12, 15, 18, 20]

for b, cfg in BATCHES.items():
    d = pd.read_csv(f"data/processed/batches/batch_{b:02d}.csv")
    print(f"\n=== Batch {b}: m_s x dTcin scan (mux={cfg['mux']}, mup={cfg['mup']}) ===", flush=True)
    best_no_crash = None
    for m_s in M_S_GRID:
        for dtcin in TCIN_GRID:
            params = {"mux": cfg["mux"], "mup": cfg["mup"], "alpha_kla": 85.0,
                      "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0,
                      "dist_flag": 1, "dist_tcin_asym": dtcin, "m_s": m_s}
            sim, _ = simulate_open_loop(b, params)
            ym = yield_metrics(sim, d)
            err = ym["rel_err_total"]
            co2d_max = sim["CO2d"].max()
            crashed = co2d_max > 7.57
            status = "CRASH" if crashed else "ok"
            if not crashed:
                if best_no_crash is None or abs(err) < abs(best_no_crash["err"]):
                    best_no_crash = {"err": err, "m_s": m_s, "dtcin": dtcin, "co2d": co2d_max}
            print(f"  m_s={m_s:.4f} dTcin={dtcin:+d}: yield={err:+.1%} CO2d={co2d_max:.2f} {status}", flush=True)
    if best_no_crash:
        print(f"  Best no-crash: m_s={best_no_crash['m_s']:.4f} dTcin={best_no_crash['dtcin']:+d} "
              f"yield={best_no_crash['err']:+.1%} CO2d={best_no_crash['co2d']:.2f}", flush=True)

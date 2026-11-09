# -*- coding: utf-8 -*-
"""3D scan m_s x mup x distTcin for batches 60 and 92 (overproduction + crash coupling).

Goal: find combination where:
- m_s low enough → S accumulates → P production matches V3
- mup low enough → P production rate reduced → less overproduction
- distTcin high enough → CO2d < 7.57 → no crash
"""
import sys, os
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from simulate import simulate_open_loop, yield_metrics

BATCHES = [60, 92]
M_S_GRID = [0.029, 0.020, 0.015, 0.010, 0.008]
MUP_GRID = [0.041, 0.030, 0.020, 0.015]
TCIN_GRID = [10, 15, 20]

for b in BATCHES:
    d = pd.read_csv(f"data/processed/batches/batch_{b:02d}.csv")
    print(f"\n=== Batch {b}: 3D scan m_s x mup x dTcin ===", flush=True)
    best_no_crash = None
    best_any = None

    for m_s in M_S_GRID:
        for mup in MUP_GRID:
            for dtcin in TCIN_GRID:
                params = {"mux": 0.47, "mup": mup, "alpha_kla": 85.0,
                          "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0,
                          "dist_flag": 1, "dist_tcin_asym": dtcin, "m_s": m_s}
                sim, _ = simulate_open_loop(b, params)
                ym = yield_metrics(sim, d)
                err = ym["rel_err_total"]
                co2d_max = sim["CO2d"].max()
                crashed = co2d_max > 7.57

                if best_any is None or abs(err) < abs(best_any["err"]):
                    best_any = {"err": err, "m_s": m_s, "mup": mup, "dtcin": dtcin, "co2d": co2d_max, "crashed": bool(crashed)}

                if not crashed:
                    if best_no_crash is None or abs(err) < abs(best_no_crash["err"]):
                        best_no_crash = {"err": err, "m_s": m_s, "mup": mup, "dtcin": dtcin, "co2d": co2d_max}

    print(f"  Best no-crash: m_s={best_no_crash['m_s']:.4f} mup={best_no_crash['mup']:.4f} "
          f"dTcin={best_no_crash['dtcin']:+d} yield={best_no_crash['err']:+.1%} CO2d={best_no_crash['co2d']:.2f}", flush=True)
    print(f"  Best any:     m_s={best_any['m_s']:.4f} mup={best_any['mup']:.4f} "
          f"dTcin={best_any['dtcin']:+d} yield={best_any['err']:+.1%} CO2d={best_any['co2d']:.2f}", flush=True)

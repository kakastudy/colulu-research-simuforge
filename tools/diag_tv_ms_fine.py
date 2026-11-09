# -*- coding: utf-8 -*-
"""时变 m_s 精细扫描：batch 27 和 92。"""
import sys, os
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from simulate import simulate_open_loop, yield_metrics

# Batch 27: base mux=0.35, mup=0.041, dTcin=+15
# Batch 92: base mux=0.47, mup=0.041, dTcin=+18

BATCHES = {
    27: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 15},
    92: {"mux": 0.47, "mup": 0.041, "dist_tcin_asym": 18},
}

# 精细网格
T_SWITCH_GRID = [120, 130, 140, 150, 160]
M_S_LATE_GRID = [0.015, 0.018, 0.020, 0.022, 0.025]

for b, base in BATCHES.items():
    d = pd.read_csv(f"data/processed/batches/batch_{b:02d}.csv")
    print(f"\n=== Batch {b}: Time-varying m_s fine scan (ms_early=0.029) ===", flush=True)

    best_no_crash = None
    for t_switch in T_SWITCH_GRID:
        for ms_late in M_S_LATE_GRID:
            params = {
                "mux": base["mux"], "mup": base["mup"],
                "alpha_kla": 85.0, "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0,
                "dist_flag": 1, "dist_tcin_asym": base["dist_tcin_asym"],
                "m_s_schedule": [(t_switch, ms_late)],
                "m_s": 0.029,
            }
            sim, _ = simulate_open_loop(b, params)
            ym = yield_metrics(sim, d)
            err = ym["rel_err_total"]
            co2d_max = sim["CO2d"].max()
            crashed = co2d_max > 7.57
            status = "CRASH" if crashed else "ok"
            if not crashed:
                if best_no_crash is None or abs(err) < abs(best_no_crash["err"]):
                    best_no_crash = {"err": err, "t_switch": t_switch, "ms_late": ms_late, "co2d": co2d_max}
            print(f"  t_sw={t_switch:3d} ms_late={ms_late:.3f}: yield={err:+.1%} CO2d={co2d_max:.2f} {status}", flush=True)

    if best_no_crash:
        print(f"\n  Best no-crash: t_switch={best_no_crash['t_switch']} ms_late={best_no_crash['ms_late']:.3f} "
              f"yield={best_no_crash['err']:+.1%} CO2d={best_no_crash['co2d']:.2f}", flush=True)

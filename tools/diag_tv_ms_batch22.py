# -*- coding: utf-8 -*-
"""Batch 22: time-varying m_s fine scan."""
import sys, os
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from simulate import simulate_open_loop, yield_metrics

d = pd.read_csv("data/processed/batches/batch_22.csv")

print("=== Batch 22: Time-varying m_s fine scan (mux=0.41, mup=0.070, dTcin=+20) ===", flush=True)
T_SWITCH_GRID = [100, 110, 120, 130, 140]
M_S_LATE_GRID = [0.008, 0.010, 0.012, 0.015, 0.018]

best_no_crash = None
for t_switch in T_SWITCH_GRID:
    for ms_late in M_S_LATE_GRID:
        params = {
            "mux": 0.41, "mup": 0.070, "alpha_kla": 85.0,
            "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0,
            "dist_flag": 1, "dist_tcin_asym": 20,
            "m_s_schedule": [(t_switch, ms_late)],
            "m_s": 0.029,
        }
        sim, _ = simulate_open_loop(22, params)
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

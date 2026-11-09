# -*- coding: utf-8 -*-
"""R129j: 批 22 m_s_schedule 精调——突破 5% 门槛。

批 22 是黄金回归唯一 yield_err > 5% 的批次（+7.0%）。R129i mux×mup 网格无法
突破。尝试调整 m_s_schedule（降速点时间和降幅值）。

当前: m_s=0.029, schedule=[(110, 0.010)] → yield_err=+7.0%
扫描: schedule_time∈{80, 100, 110, 120, 140} × schedule_val∈{0.005, 0.010, 0.015, 0.020}
= 20 仿真
"""
import io
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))

import numpy as np
import pandas as pd

from simulate import simulate_open_loop, yield_metrics


def build_params(mux, mup, m_s, sched_time, sched_val):
    p = {"mux": mux, "mup": mup, "alpha_kla": 85.0,
         "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0,
         "dist_flag": 1, "dist_tcin_asym": 20, "m_s": m_s}
    if sched_time > 0:
        p["m_s_schedule"] = [(sched_time, sched_val)]
    return p


def main():
    b = 22
    v3 = pd.read_csv(f"data/processed/batches/batch_{b:02d}.csv")

    # Baseline
    sim_base, _ = simulate_open_loop(b, build_params(0.35, 0.065, 0.029, 110, 0.010))
    ye_base = yield_metrics(sim_base, v3)["rel_err_total"]
    print("Batch 22 baseline: yield_err=%.4f (m_s=0.029 sched=[(110,0.010)])" % ye_base, flush=True)

    results = {}
    print("\nm_s_schedule sweep:", flush=True)

    for sched_time in [80, 100, 110, 120, 140]:
        for sched_val in [0.005, 0.010, 0.015, 0.020]:
            sim, _ = simulate_open_loop(b, build_params(0.35, 0.065, 0.029, sched_time, sched_val))
            ye = yield_metrics(sim, v3)["rel_err_total"]
            key = f"st{sched_time}_sv{sched_val}"
            results[key] = {"yield_err": round(ye, 4), "sched_time": sched_time, "sched_val": sched_val}
            if abs(ye) < 0.05:
                print("  %s: yield_err=%.4f ★ (within 5%!)" % (key, ye), flush=True)
            elif abs(ye) < abs(ye_base):
                print("  %s: yield_err=%.4f (improvement)" % (key, ye), flush=True)

    best_key = min(results.items(), key=lambda x: abs(x[1]["yield_err"]))
    print("\nBEST: %s → yield_err=%.4f (sched_time=%d sched_val=%.3f)" % (
        best_key[0], best_key[1]["yield_err"], best_key[1]["sched_time"], best_key[1]["sched_val"]), flush=True)

    # Also try without schedule
    sim_nosched, _ = simulate_open_loop(b, build_params(0.35, 0.065, 0.029, 0, 0))
    ye_nosched = yield_metrics(sim_nosched, v3)["rel_err_total"]
    print("No schedule: yield_err=%.4f" % ye_nosched, flush=True)
    results["nosched"] = {"yield_err": round(ye_nosched, 4)}

    # Compute RMSE
    other_ye = {8: 0.0038, 11: 0.0025, 16: 0.0041, 23: 0.0006, 27: -0.0019,
                36: -0.0447, 55: -0.0191, 60: 0.0155, 80: -0.0007, 91: 0.0437, 92: -0.0033}
    all_ye = dict(other_ye)
    all_ye[22] = best_key[1]["yield_err"]
    rmse_new = float(np.sqrt(np.mean([e ** 2 for e in all_ye.values()])))
    print("\nRMSE with best batch 22: {:.4f} (R129i: 2.80%)".format(rmse_new), flush=True)

    dst = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "runs", "p3", "d9_death_term_batch22_sched.json")
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("Saved: %s" % dst, flush=True)


if __name__ == "__main__":
    main()

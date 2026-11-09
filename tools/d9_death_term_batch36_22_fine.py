# -*- coding: utf-8 -*-
"""R129h: 批 36/22 参数精调——进一步降低 RMSE。

D9 目标已达成(RMSE 3.12% < 3.5%)。R129h 继续优化剩余 2 批以进一步降低 RMSE。

批 36: yield_err=-6.4%（模型低估产量）→ 升 mup 或降 m_s
  当前: mux=0.41 mup=0.041 m_s=0.015
  扫描: mup∈{0.041,0.045,0.050,0.055,0.060} × m_s∈{0.005,0.008,0.010,0.015} = 20 仿真

批 22: yield_err=+7.1%（模型高估产量）→ 降 mup 或升 m_s
  当前: mux=0.35 mup=0.070 m_s=0.029 m_s_schedule=[(110,0.010)]
  扫描: mup∈{0.060,0.065,0.070,0.075} × m_s∈{0.029,0.035,0.040,0.045} = 16 仿真
"""
import io
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))

import numpy as np
import pandas as pd

from simulate import simulate_open_loop, yield_metrics


def build_params_36(mux, mup, m_s):
    return {"mux": mux, "mup": mup, "alpha_kla": 85.0,
            "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0,
            "dist_flag": 1, "dist_tcin_asym": 10, "m_s": m_s}


def build_params_22(mux, mup, m_s):
    return {"mux": mux, "mup": mup, "alpha_kla": 85.0,
            "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0,
            "dist_flag": 1, "dist_tcin_asym": 20, "m_s": m_s,
            "m_s_schedule": [(110, 0.010)]}


def main():
    results = {}
    print("=" * 80, flush=True)
    print("R129h: 批 36/22 参数精调", flush=True)
    print("=" * 80, flush=True)

    # Batch 36
    b = 36
    v3 = pd.read_csv(f"data/processed/batches/batch_{b:02d}.csv")
    sim_base, _ = simulate_open_loop(b, build_params_36(0.41, 0.041, 0.015))
    ye_base = yield_metrics(sim_base, v3)["rel_err_total"]
    print("Batch 36 baseline: yield_err=%.4f" % ye_base, flush=True)

    br36 = {}
    for mup in [0.041, 0.045, 0.050, 0.055, 0.060]:
        for m_s in [0.005, 0.008, 0.010, 0.015]:
            sim, _ = simulate_open_loop(b, build_params_36(0.41, mup, m_s))
            ye = yield_metrics(sim, v3)["rel_err_total"]
            key = f"mup{mup}_ms{m_s}"
            br36[key] = {"yield_err": round(ye, 4), "mup": mup, "m_s": m_s}
            if abs(ye) < abs(ye_base) and abs(ye) <= 0.03:
                print("  %s: yield_err=%.4f ★" % (key, ye), flush=True)

    best36 = min(br36.items(), key=lambda x: abs(x[1]["yield_err"]))
    print("  BEST: %s → yield_err=%.4f" % (best36[0], best36[1]["yield_err"]), flush=True)
    results["36"] = {"baseline": ye_base, "results": br36,
                     "best": best36[0], "best_yield_err": best36[1]["yield_err"]}

    # Batch 22
    b = 22
    v3 = pd.read_csv(f"data/processed/batches/batch_{b:02d}.csv")
    sim_base, _ = simulate_open_loop(b, build_params_22(0.35, 0.070, 0.029))
    ye_base = yield_metrics(sim_base, v3)["rel_err_total"]
    print("\nBatch 22 baseline: yield_err=%.4f" % ye_base, flush=True)

    br22 = {}
    for mup in [0.060, 0.065, 0.070, 0.075]:
        for m_s in [0.029, 0.035, 0.040, 0.045]:
            sim, _ = simulate_open_loop(b, build_params_22(0.35, mup, m_s))
            ye = yield_metrics(sim, v3)["rel_err_total"]
            key = f"mup{mup}_ms{m_s}"
            br22[key] = {"yield_err": round(ye, 4), "mup": mup, "m_s": m_s}
            if abs(ye) < abs(ye_base) and abs(ye) <= 0.05:
                print("  %s: yield_err=%.4f ★" % (key, ye), flush=True)

    best22 = min(br22.items(), key=lambda x: abs(x[1]["yield_err"]))
    print("  BEST: %s → yield_err=%.4f" % (best22[0], best22[1]["yield_err"]), flush=True)
    results["22"] = {"baseline": ye_base, "results": br22,
                     "best": best22[0], "best_yield_err": best22[1]["yield_err"]}

    # Compute RMSE with best configs
    other_ye = {8: 0.0038, 11: 0.0025, 16: 0.0041, 23: 0.0006, 27: -0.0019,
                55: -0.0191, 60: 0.0155, 80: -0.0007, 91: 0.0437, 92: -0.0033}
    all_ye = dict(other_ye)
    all_ye[36] = results["36"]["best_yield_err"]
    all_ye[22] = results["22"]["best_yield_err"]
    rmse_new = float(np.sqrt(np.mean([e ** 2 for e in all_ye.values()])))
    print("\nRMSE with best configs: {:.4f} (R129g2: 3.12%)".format(rmse_new), flush=True)

    dst = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "runs", "p3", "d9_death_term_batch36_22_fine.json")
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("Saved: %s" % dst, flush=True)


if __name__ == "__main__":
    main()

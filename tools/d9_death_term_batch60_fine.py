# -*- coding: utf-8 -*-
"""R129g2: 批 60 精细参数调优——mup×m_s 网格。

R129g 发现批 60 yield_err=-9.2%（模型低估产量 9.2%）。降 mux 0.47→0.40 改善至
-5.97% 但仍不足。需更精细调 mup（升高以增加产物合成）和 m_s（降低以减少维持消耗）。

批 60 当前: mux=0.47 mup=0.030 m_s=0.025 → yield_err=-9.2%
R129g 最优: mux=0.40 mup=0.030 m_s=0.025 → yield_err=-6.0%

扫描 mup∈{0.030, 0.035, 0.040, 0.045, 0.050} × m_s∈{0.010, 0.015, 0.020, 0.025, 0.030}
× mux∈{0.40, 0.43, 0.47} = 75 仿真
"""
import io
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))

import numpy as np
import pandas as pd

from simulate import simulate_open_loop, yield_metrics


def build_params(mux, mup, m_s):
    return {"mux": mux, "mup": mup, "alpha_kla": 85.0,
            "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0,
            "dist_flag": 1, "dist_tcin_asym": 15, "m_s": m_s}


def main():
    b = 60
    v3 = pd.read_csv(f"data/processed/batches/batch_{b:02d}.csv")

    # Baseline
    sim_base, _ = simulate_open_loop(b, build_params(0.47, 0.030, 0.025))
    ye_base = yield_metrics(sim_base, v3)["rel_err_total"]
    print("Batch 60 baseline: yield_err=%.4f (mux=0.47 mup=0.030 m_s=0.025)" % ye_base, flush=True)

    results = {}
    print("\nmup × m_s × mux sweep (yield_err):", flush=True)

    for mup in [0.030, 0.035, 0.040, 0.045, 0.050]:
        for m_s in [0.010, 0.015, 0.020, 0.025, 0.030]:
            for mux in [0.40, 0.43, 0.47]:
                sim, _ = simulate_open_loop(b, build_params(mux, mup, m_s))
                ye = yield_metrics(sim, v3)["rel_err_total"]
                key = f"mux{mux}_mup{mup}_ms{m_s}"
                results[key] = {"yield_err": round(ye, 4), "mux": mux, "mup": mup, "m_s": m_s}
                if abs(ye) < 0.03:
                    print("  %s: yield_err=%.4f ★" % (key, ye), flush=True)

    # Find best
    best_key = None
    best_abs = 1e9
    for key, r in results.items():
        if abs(r["yield_err"]) < best_abs:
            best_abs = abs(r["yield_err"])
            best_key = key
    r = results[best_key]
    print("\nBEST: %s → yield_err=%.4f (mux=%.2f mup=%.3f m_s=%.3f)" % (
        best_key, r["yield_err"], r["mux"], r["mup"], r["m_s"]), flush=True)

    # Compute new RMSE
    other_ye = {8: 0.0038, 11: 0.0025, 16: 0.0041, 22: 0.0713, 23: 0.0006,
                27: -0.0019, 36: -0.0637, 55: -0.0191, 80: -0.0007,
                91: 0.0437, 92: -0.0033}
    all_ye = dict(other_ye)
    all_ye[60] = r["yield_err"]
    rmse_new = float(np.sqrt(np.mean([e ** 2 for e in all_ye.values()])))
    print("RMSE with best batch 60: {:.4f} (target: 3.50%)".format(rmse_new), flush=True)

    dst = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "runs", "p3", "d9_death_term_batch60_fine.json")
    with open(dst, "w", encoding="utf-8") as f:
        json.dump({"results": results, "best_config": best_key,
                   "rmse_with_best": rmse_new}, f, ensure_ascii=False, indent=2)
    print("Saved: %s" % dst, flush=True)


if __name__ == "__main__":
    main()

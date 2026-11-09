# -*- coding: utf-8 -*-
"""R129i: 批 22/36/91 联合 mux×mup 网格——进一步降低 RMSE。

D9 已达成(RMSE 2.96%)。R129i 继续优化剩余 3 批以进一步降低 RMSE。

批 22 (yield_err=+7.0%, 模型高估): mux∈{0.30,0.32,0.35,0.38,0.40} × mup∈{0.055,0.060,0.065,0.070}
批 36 (yield_err=-5.6%, 模型低估): mux∈{0.38,0.41,0.44,0.47} × mup∈{0.045,0.050,0.055,0.060}
批 91 (yield_err=+4.4%, 模型高估): mux∈{0.35,0.39,0.43} × mup∈{0.035,0.041,0.045}

注意：批 91 有死亡项(kd=0.005 ds=200)，参数变化会与死亡项交互。
"""
import io
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))

import numpy as np
import pandas as pd

from simulate import simulate_open_loop, yield_metrics


def build_params_22(mux, mup):
    return {"mux": mux, "mup": mup, "alpha_kla": 85.0,
            "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0,
            "dist_flag": 1, "dist_tcin_asym": 20, "m_s": 0.029,
            "m_s_schedule": [(110, 0.010)]}


def build_params_36(mux, mup):
    return {"mux": mux, "mup": mup, "alpha_kla": 85.0,
            "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0,
            "dist_flag": 1, "dist_tcin_asym": 10, "m_s": 0.010}


def build_params_91(mux, mup):
    return {"mux": mux, "mup": mup, "alpha_kla": 85.0,
            "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0,
            "dist_flag": 1, "dist_tcin_asym": 10, "m_s": 0.029,
            "biomass_death_rate": 0.005, "death_start": 200}


def main():
    results = {}
    print("=" * 80, flush=True)
    print("R129i: 批 22/36/91 联合 mux×mup 网格", flush=True)
    print("=" * 80, flush=True)

    configs = {
        22: {"build": build_params_22,
             "mux": [0.30, 0.32, 0.35, 0.38, 0.40],
             "mup": [0.055, 0.060, 0.065, 0.070],
             "current": (0.35, 0.065), "baseline_ye": 0.070},
        36: {"build": build_params_36,
             "mux": [0.38, 0.41, 0.44, 0.47],
             "mup": [0.045, 0.050, 0.055, 0.060],
             "current": (0.41, 0.050), "baseline_ye": -0.056},
        91: {"build": build_params_91,
             "mux": [0.35, 0.39, 0.43],
             "mup": [0.035, 0.041, 0.045],
             "current": (0.39, 0.041), "baseline_ye": 0.044},
    }

    for b in [22, 36, 91]:
        cfg = configs[b]
        v3 = pd.read_csv(f"data/processed/batches/batch_{b:02d}.csv")
        sim_base, _ = simulate_open_loop(b, cfg["build"](*cfg["current"]))
        ye_base = yield_metrics(sim_base, v3)["rel_err_total"]
        print("Batch %2d baseline: yield_err=%.4f (mux=%.2f mup=%.3f)" % (
            b, ye_base, cfg["current"][0], cfg["current"][1]), flush=True)

        batch_results = {}
        for mux in cfg["mux"]:
            for mup in cfg["mup"]:
                sim, _ = simulate_open_loop(b, cfg["build"](mux, mup))
                ye = yield_metrics(sim, v3)["rel_err_total"]
                key = f"mux{mux}_mup{mup}"
                batch_results[key] = {"yield_err": round(ye, 4), "mux": mux, "mup": mup}
                if abs(ye) < 0.03:
                    print("  %s: yield_err=%.4f ★" % (key, ye), flush=True)

        best_key = min(batch_results.items(), key=lambda x: abs(x[1]["yield_err"]))
        print("  BEST: %s → yield_err=%.4f (mux=%.2f mup=%.3f)" % (
            best_key[0], best_key[1]["yield_err"], best_key[1]["mux"], best_key[1]["mup"]), flush=True)
        results[str(b)] = {"baseline": ye_base, "results": batch_results,
                           "best": best_key[0], "best_yield_err": best_key[1]["yield_err"]}

    # Compute RMSE with best configs
    other_ye = {8: 0.0038, 11: 0.0025, 16: 0.0041, 23: 0.0006, 27: -0.0019,
                55: -0.0191, 60: 0.0155, 80: -0.0007, 92: -0.0033}
    all_ye = dict(other_ye)
    for b_str in ["22", "36", "91"]:
        all_ye[int(b_str)] = results[b_str]["best_yield_err"]
    rmse_new = float(np.sqrt(np.mean([e ** 2 for e in all_ye.values()])))
    print("\nRMSE with best configs: {:.4f} (R129h: 2.96%)".format(rmse_new), flush=True)

    dst = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "runs", "p3", "d9_death_term_batch22_36_91_grid.json")
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("Saved: %s" % dst, flush=True)


if __name__ == "__main__":
    main()

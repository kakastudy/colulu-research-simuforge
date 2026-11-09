# -*- coding: utf-8 -*-
"""R129g: 产量级 RMSE≤3.5% 攻坚——批 60/36/22 参数精调。

R129f 完成后黄金回归 RMSE=4.15%（死亡项贡献 4.48%→4.15%）。剩余差距由 3 批主导：
- 批 60: yield_err=-9.2%（模型高估产量 9.2%）→ mup 偏低仍高估 → 需降 mup 或 mux
- 批 36: yield_err=-6.4%（模型高估产量 6.4%）→ 同上
- 批 22: yield_err=+7.7%（模型低估产量 7.7%）→ 需升 mup 或 mux

扫描 3 批 × mup×mux 网格，找 yield_err 接近 0 的组合。
批 60: mup∈{0.020, 0.025, 0.030, 0.035} × mux∈{0.40, 0.43, 0.47, 0.50}
批 36: mup∈{0.030, 0.035, 0.041, 0.045} × mux∈{0.35, 0.38, 0.41, 0.44}
批 22: mup∈{0.060, 0.070, 0.080, 0.090} × mux∈{0.35, 0.38, 0.41, 0.44}
"""
import io
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))

import numpy as np
import pandas as pd

from simulate import simulate_open_loop, yield_metrics


COMBINED = {
    8:  {"mux": 0.47, "mup": 0.041, "dist_tcin_asym": 10, "m_s": 0.029,
          "biomass_death_rate": 0.001, "death_start": 100},
    11: {"mux": 0.41, "mup": 0.041, "dist_tcin_asym": 10, "m_s": 0.020},
    16: {"mux": 0.41, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.025,
          "biomass_death_rate": 0.005, "death_start": 0},
    22: {"mux": 0.41, "mup": 0.070, "dist_tcin_asym": 20, "m_s": 0.029,
          "m_s_schedule": [(110, 0.010)]},
    23: {"mux": 0.35, "mup": 0.070, "dist_tcin_asym": 10, "m_s": 0.029,
          "biomass_death_rate": 0.0005, "death_start": 200},
    27: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 15, "m_s": 0.029,
          "m_s_schedule": [(140, 0.018)]},
    36: {"mux": 0.41, "mup": 0.041, "dist_tcin_asym": 10, "m_s": 0.015},
    55: {"mux": 0.47, "mup": 0.055, "dist_tcin_asym": 20, "m_s": 0.025,
          "biomass_death_rate": 0.001, "death_start": 200},
    60: {"mux": 0.47, "mup": 0.030, "dist_tcin_asym": 15, "m_s": 0.025},
    80: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 18, "m_s": 0.029,
          "biomass_death_rate": 0.005, "death_start": 0},
    91: {"mux": 0.39, "mup": 0.041, "dist_tcin_asym": 10, "m_s": 0.029,
          "biomass_death_rate": 0.005, "death_start": 200},
    92: {"mux": 0.47, "mup": 0.041, "dist_tcin_asym": 18, "m_s": 0.029,
          "m_s_schedule": [(150, 0.015)],
          "biomass_death_rate": 0.005, "death_start": 200},
}


def build_params(b, cp, mux=None, mup=None):
    p = {"mux": cp["mux"] if mux is None else mux,
         "mup": cp["mup"] if mup is None else mup,
         "alpha_kla": 85.0,
         "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0,
         "dist_flag": 1, "dist_tcin_asym": cp["dist_tcin_asym"], "m_s": cp["m_s"]}
    if "m_s_schedule" in cp:
        p["m_s_schedule"] = cp["m_s_schedule"]
    if "biomass_death_rate" in cp:
        p["biomass_death_rate"] = cp["biomass_death_rate"]
        p["death_start"] = cp["death_start"]
    return p


def main():
    results = {}
    print("=" * 80, flush=True)
    print("R129g: 产量级 RMSE≤3.5% 攻坚——批 60/36/22 参数精调", flush=True)
    print("=" * 80, flush=True)

    sweeps = {
        60: {"mup": [0.020, 0.025, 0.030, 0.035], "mux": [0.40, 0.43, 0.47, 0.50]},
        36: {"mup": [0.030, 0.035, 0.041, 0.045], "mux": [0.35, 0.38, 0.41, 0.44]},
        22: {"mup": [0.060, 0.070, 0.080, 0.090], "mux": [0.35, 0.38, 0.41, 0.44]},
    }

    for b in [60, 36, 22]:
        v3 = pd.read_csv(f"data/processed/batches/batch_{b:02d}.csv")
        cp = COMBINED[b]

        # Baseline
        sim_base, _ = simulate_open_loop(b, build_params(b, cp))
        ye_base = yield_metrics(sim_base, v3)["rel_err_total"]
        print("Batch %2d baseline: yield_err=%.4f (mux=%.2f mup=%.3f)" % (
            b, ye_base, cp["mux"], cp["mup"]), flush=True)

        batch_results = {"baseline": {"yield_err": round(ye_base, 4),
                                       "mux": cp["mux"], "mup": cp["mup"]}}
        for mup in sweeps[b]["mup"]:
            for mux in sweeps[b]["mux"]:
                sim, _ = simulate_open_loop(b, build_params(b, cp, mux, mup))
                ye = yield_metrics(sim, v3)["rel_err_total"]
                key = f"mux{mux}_mup{mup}"
                batch_results[key] = {"yield_err": round(ye, 4),
                                       "mux": mux, "mup": mup}
                if abs(ye) < 0.03:
                    print("  %s: yield_err=%.4f ★" % (key, ye), flush=True)

        # Find best
        best_key = None
        best_abs = 1e9
        for key, r in batch_results.items():
            if key == "baseline":
                continue
            if abs(r["yield_err"]) < best_abs:
                best_abs = abs(r["yield_err"])
                best_key = key
        if best_key:
            r = batch_results[best_key]
            print("  BEST: %s → yield_err=%.4f (mux=%.2f mup=%.3f)" % (
                best_key, r["yield_err"], r["mux"], r["mup"]), flush=True)

        results[str(b)] = batch_results
        print(flush=True)

    # Summary: compute RMSE with best configs
    print("=" * 80, flush=True)
    print("Summary:", flush=True)
    all_ye = []
    best_configs = {}
    for b_str in ["60", "36", "22"]:
        br = results[b_str]
        best_key = None
        best_abs = 1e9
        for key, r in br.items():
            if key == "baseline":
                continue
            if abs(r["yield_err"]) < best_abs:
                best_abs = abs(r["yield_err"])
                best_key = key
        if best_key:
            r = br[best_key]
            best_configs[b_str] = best_key
            all_ye.append(r["yield_err"])
            print("  Batch %s: %s → yield_err=%.4f (mux=%.2f mup=%.3f)" % (
                b_str, best_key, r["yield_err"], r["mux"], r["mup"]), flush=True)
        else:
            all_ye.append(br["baseline"]["yield_err"])

    # Compute new RMSE with best configs for these 3 batches
    # Other 9 batches stay at R129f values
    other_ye = {8: 0.0038, 11: 0.0025, 16: 0.0041, 23: 0.0006, 27: -0.0019,
                55: -0.0191, 80: -0.0007, 91: 0.0437, 92: -0.0033}
    all_ye_dict = dict(other_ye)
    all_ye_dict[60] = all_ye[0]
    all_ye_dict[36] = all_ye[1]
    all_ye_dict[22] = all_ye[2]

    rmse_new = float(np.sqrt(np.mean([e ** 2 for e in all_ye_dict.values()])))
    print("\nRMSE with best configs: {:.4f} (R129f: 4.15%, target: 3.50%)".format(rmse_new), flush=True)

    dst = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "runs", "p3", "d9_death_term_yield_tuning.json")
    with open(dst, "w", encoding="utf-8") as f:
        json.dump({"results": results, "best_configs": best_configs,
                   "rmse_with_best": rmse_new}, f, ensure_ascii=False, indent=2)
    print("Saved: %s" % dst, flush=True)


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""R129f: 衰亡项 COMBINED 语境校准——12 批逐批最优 kd。

R129d/e 校准在 calib_params 语境（含 PAA_CAL），但黄金回归用 COMBINED dict
（不含 PAA_CAL），语境不同 → 衰亡项效果不同。R129f 直接在 COMBINED 语境下
逐批扫描 kd，找 yield_err 最优值。

COMBINED 基线 yield_err：8:+1.5% 11:+0.3% 16:+4.3% 22:+7.7% 23:-0.4%
  27:-0.2% 36:-6.4% 55:-2.6% 60:-9.2% 80:+3.0% 91:+4.5% 92:-0.6%
RMSE=4.48%。D9 目标 RMSE≤3.5%。

扫描 12 批 × kd∈{0, 0.0005, 0.001, 0.002, 0.003, 0.005} × ds∈{0, 100, 200} = 216 仿真
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
    8:  {"mux": 0.47, "mup": 0.041, "dist_tcin_asym": 10, "m_s": 0.029},
    11: {"mux": 0.41, "mup": 0.041, "dist_tcin_asym": 10, "m_s": 0.020},
    16: {"mux": 0.41, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.025},
    22: {"mux": 0.41, "mup": 0.070, "dist_tcin_asym": 20, "m_s": 0.029,
          "m_s_schedule": [(110, 0.010)]},
    23: {"mux": 0.35, "mup": 0.070, "dist_tcin_asym": 10, "m_s": 0.029},
    27: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 15, "m_s": 0.029,
          "m_s_schedule": [(140, 0.018)]},
    36: {"mux": 0.41, "mup": 0.041, "dist_tcin_asym": 10, "m_s": 0.015},
    55: {"mux": 0.47, "mup": 0.055, "dist_tcin_asym": 20, "m_s": 0.025},
    60: {"mux": 0.47, "mup": 0.030, "dist_tcin_asym": 15, "m_s": 0.025},
    80: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 18, "m_s": 0.029},
    91: {"mux": 0.39, "mup": 0.041, "dist_tcin_asym": 10, "m_s": 0.029},
    92: {"mux": 0.47, "mup": 0.041, "dist_tcin_asym": 18, "m_s": 0.029,
          "m_s_schedule": [(150, 0.015)]},
}

GOLDEN = [8, 11, 16, 22, 23, 27, 36, 55, 60, 80, 91, 92]


def build_params(b, cp, kd=0.0, ds=0.0):
    p = {"mux": cp["mux"], "mup": cp["mup"], "alpha_kla": 85.0,
         "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0,
         "dist_flag": 1, "dist_tcin_asym": cp["dist_tcin_asym"], "m_s": cp["m_s"]}
    if "m_s_schedule" in cp:
        p["m_s_schedule"] = cp["m_s_schedule"]
    if kd > 0:
        p["biomass_death_rate"] = kd
        p["death_start"] = ds
    return p


def main():
    results = {}
    print("=" * 80, flush=True)
    print("R129f: 衰亡项 COMBINED 语境校准", flush=True)
    print("=" * 80, flush=True)

    for b in GOLDEN:
        v3 = pd.read_csv(f"data/processed/batches/batch_{b:02d}.csv")
        cp = COMBINED[b]

        # Baseline
        params_base = build_params(b, cp)
        sim_base, _ = simulate_open_loop(b, params_base)
        ym_base = yield_metrics(sim_base, v3)
        ye_base = ym_base["rel_err_total"]
        print("Batch %2d baseline: yield_err=%.4f" % (b, ye_base), flush=True)

        batch_results = {"baseline": {"yield_err": round(ye_base, 4)}}
        for kd in [0.0005, 0.001, 0.002, 0.003, 0.005]:
            for ds in [0, 100, 200]:
                params = build_params(b, cp, kd, ds)
                sim, _ = simulate_open_loop(b, params)
                ym = yield_metrics(sim, v3)
                ye = ym["rel_err_total"]
                key = f"kd{kd}_ds{ds}"
                batch_results[key] = {"yield_err": round(ye, 4)}
                # Show promising configs: yield error reduced
                if abs(ye) < abs(ye_base) and abs(ye) <= 0.05:
                    print("  %s: yield_err=%.4f (from %.4f, improvement)" % (
                        key, ye, ye_base), flush=True)

        # Find best config: minimize |yield_err|
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
            delta = ye_base - r["yield_err"]
            print("  BEST: %s → yield_err=%.4f (from %.4f, Δ=%.4f)" % (
                best_key, r["yield_err"], ye_base, delta), flush=True)

        results[str(b)] = batch_results
        print(flush=True)

    # Summary: compute RMSE with best configs
    print("=" * 80, flush=True)
    print("Summary: RMSE with best per-batch configs:", flush=True)
    all_ye = []
    best_configs = {}
    for b_str, br in results.items():
        best_key = None
        best_abs = 1e9
        for key, r in br.items():
            if key == "baseline":
                continue
            if abs(r["yield_err"]) < best_abs:
                best_abs = abs(r["yield_err"])
                best_key = key
        if best_key and abs(br[best_key]["yield_err"]) < abs(br["baseline"]["yield_err"]):
            best_configs[b_str] = best_key
            all_ye.append(br[best_key]["yield_err"])
            print("  Batch %s: %s → yield_err=%.4f (from %.4f)" % (
                b_str, best_key, br[best_key]["yield_err"], br["baseline"]["yield_err"]), flush=True)
        else:
            all_ye.append(br["baseline"]["yield_err"])
            print("  Batch %s: baseline (no improvement) → yield_err=%.4f" % (
                b_str, br["baseline"]["yield_err"]), flush=True)

    rmse = float(np.sqrt(np.mean([e ** 2 for e in all_ye])))
    print("\nRMSE with best configs: %.4f (baseline 4.48%)" % rmse, flush=True)

    dst = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "runs", "p3", "d9_death_term_combined_ctx.json")
    with open(dst, "w", encoding="utf-8") as f:
        json.dump({"results": results, "best_configs": best_configs,
                   "rmse_with_best": rmse}, f, ensure_ascii=False, indent=2)
    print("Saved: %s" % dst, flush=True)


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""R129r2: vis_scale 逐批校准——最小化黏度 nRMSE，检查产量影响。

vis_scale 默认 1.0（黄金回归零影响）。
扫描 vis_scale∈{0.5, 0.6, 0.7, 0.8, 0.9, 1.0} × 12 批。
"""
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
    22: {"mux": 0.35, "mup": 0.065, "dist_tcin_asym": 20, "m_s": 0.029,
          "m_s_schedule": [(110, 0.010)]},
    23: {"mux": 0.35, "mup": 0.070, "dist_tcin_asym": 10, "m_s": 0.029,
          "biomass_death_rate": 0.0005, "death_start": 200},
    27: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 15, "m_s": 0.029,
          "m_s_schedule": [(140, 0.018)]},
    36: {"mux": 0.47, "mup": 0.045, "dist_tcin_asym": 10, "m_s": 0.010},
    55: {"mux": 0.47, "mup": 0.055, "dist_tcin_asym": 20, "m_s": 0.025,
          "biomass_death_rate": 0.001, "death_start": 200},
    60: {"mux": 0.47, "mup": 0.035, "dist_tcin_asym": 15, "m_s": 0.010},
    80: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 18, "m_s": 0.029,
          "biomass_death_rate": 0.005, "death_start": 0},
    91: {"mux": 0.39, "mup": 0.041, "dist_tcin_asym": 10, "m_s": 0.029,
          "biomass_death_rate": 0.005, "death_start": 200},
    92: {"mux": 0.47, "mup": 0.041, "dist_tcin_asym": 18, "m_s": 0.029,
          "m_s_schedule": [(150, 0.015)],
          "biomass_death_rate": 0.005, "death_start": 200},
}

GOLDEN = [8, 11, 16, 22, 23, 27, 36, 55, 60, 80, 91, 92]


def build_params(cp, vis_scale=1.0):
    params = {"mux": cp["mux"], "mup": cp["mup"], "alpha_kla": 85.0,
              "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0,
              "dist_flag": 1, "dist_tcin_asym": cp["dist_tcin_asym"], "m_s": cp["m_s"],
              "vis_scale": vis_scale}
    if "m_s_schedule" in cp:
        params["m_s_schedule"] = cp["m_s_schedule"]
    if "biomass_death_rate" in cp:
        params["biomass_death_rate"] = cp["biomass_death_rate"]
        params["death_start"] = cp["death_start"]
    return params


def main():
    print("=" * 80, flush=True)
    print("R129r2: vis_scale 逐批校准", flush=True)
    print("=" * 80, flush=True)

    vis_scales = [0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    results = {}

    for b in GOLDEN:
        v3 = pd.read_csv(f"data/processed/batches/batch_{b:02d}.csv")
        cp = COMBINED[b]

        best_vs = 1.0
        best_nrmse = float('inf')
        best_yield = 0.0

        for vs in vis_scales:
            params = build_params(cp, vs)
            sim, _ = simulate_open_loop(b, params)

            v3_vis = v3['Viscosity_offline'].to_numpy(float)
            sim_vis = sim['vis'].to_numpy(float)
            n = min(len(v3_vis), len(sim_vis))
            v3_vis = v3_vis[:n]
            sim_vis = sim_vis[:n]

            valid = ~np.isnan(v3_vis)
            v3_v = v3_vis[valid]
            sim_v = sim_vis[valid]

            rmse = float(np.sqrt(np.mean((sim_v - v3_v) ** 2)))
            nrmse = rmse / np.mean(v3_v) * 100 if np.mean(v3_v) > 1e-10 else 0

            ym = yield_metrics(sim, v3)
            yield_err = ym["rel_err_total"]

            if nrmse < best_nrmse:
                best_nrmse = nrmse
                best_vs = vs
                best_yield = yield_err

            results.setdefault(str(b), {})[str(vs)] = {
                "vis_nrmse": round(nrmse, 2),
                "yield_err": round(yield_err, 4),
            }

        # Also get baseline (vs=1.0) yield for comparison
        params_base = build_params(cp, 1.0)
        sim_base, _ = simulate_open_loop(b, params_base)
        ym_base = yield_metrics(sim_base, v3)
        yield_base = ym_base["rel_err_total"]

        print("  Batch {:2d}: best_vis_scale={:.1f} vis_nRMSE={:.1f}% "
              "yield={:+.4f} (base {:+.4f})".format(
                  b, best_vs, best_nrmse, best_yield, yield_base), flush=True)

    dst = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "runs", "p3", "d9_vis_scale_calibration.json")
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("\nSaved: %s" % dst, flush=True)


if __name__ == "__main__":
    main()

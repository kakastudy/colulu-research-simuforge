# -*- coding: utf-8 -*-
"""R129y: Y_NX/Y_NP 逐批校准——改善 NH3_offline 通道。

Y_NX (par[70]=10) 和 Y_NP (par[71]=80) 仅出现在 NH3 ODE 中：
  X_C_nitrogen = (-r_b0 - r_e1 - r_d1 - r_d4) * Y_NX
  P_C_nitrogen = -dP_dt * Y_NP
不出现在任何生长/底物 ODE 中。NH3_inhib 在全部 12 批饱和于 1.0（NH3~1700 >> X_crit_N=150）。
→ Y_NX/Y_NP 是休眠机制——可自由调以改善 NH3_offline，产量零影响。
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
          "biomass_death_rate": 0.001, "death_start": 100, "q_co2": 0.12},
    11: {"mux": 0.41, "mup": 0.041, "dist_tcin_asym": 10, "m_s": 0.020, "q_co2": 0.11},
    16: {"mux": 0.41, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.025,
          "biomass_death_rate": 0.005, "death_start": 0, "q_co2": 0.14},
    22: {"mux": 0.35, "mup": 0.065, "dist_tcin_asym": 20, "m_s": 0.029,
          "m_s_schedule": [(110, 0.010)], "q_co2": 0.12},
    23: {"mux": 0.35, "mup": 0.070, "dist_tcin_asym": 10, "m_s": 0.029,
          "biomass_death_rate": 0.0005, "death_start": 200, "q_co2": 0.10},
    27: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 15, "m_s": 0.029,
          "m_s_schedule": [(140, 0.018)], "q_co2": 0.12},
    36: {"mux": 0.47, "mup": 0.045, "dist_tcin_asym": 10, "m_s": 0.010, "q_co2": 0.10},
    55: {"mux": 0.47, "mup": 0.055, "dist_tcin_asym": 20, "m_s": 0.025,
          "biomass_death_rate": 0.001, "death_start": 200, "q_co2": 0.11},
    60: {"mux": 0.47, "mup": 0.035, "dist_tcin_asym": 15, "m_s": 0.010, "q_co2": 0.10},
    80: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 18, "m_s": 0.029,
          "biomass_death_rate": 0.005, "death_start": 0, "q_co2": 0.13},
    91: {"mux": 0.39, "mup": 0.041, "dist_tcin_asym": 10, "m_s": 0.029,
          "biomass_death_rate": 0.005, "death_start": 200, "q_co2": 0.12},
    92: {"mux": 0.47, "mup": 0.041, "dist_tcin_asym": 18, "m_s": 0.029,
          "m_s_schedule": [(150, 0.015)],
          "biomass_death_rate": 0.005, "death_start": 200, "q_co2": 0.11},
}

GOLDEN = [8, 11, 16, 22, 23, 27, 36, 55, 60, 80, 91, 92]


def build_params(cp, y_nx=None, y_np=None):
    params = {"mux": cp["mux"], "mup": cp["mup"], "alpha_kla": 85.0,
              "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0,
              "dist_flag": 1, "dist_tcin_asym": cp["dist_tcin_asym"], "m_s": cp["m_s"],
              "q_co2": cp["q_co2"]}
    if "m_s_schedule" in cp:
        params["m_s_schedule"] = cp["m_s_schedule"]
    if "biomass_death_rate" in cp:
        params["biomass_death_rate"] = cp["biomass_death_rate"]
        params["death_start"] = cp["death_start"]
    if y_nx is not None:
        params["Y_NX"] = y_nx
    if y_np is not None:
        params["Y_NP"] = y_np
    return params


def compute_channel_nrmse(sim, v3, sim_col, v3_col):
    """Compute nRMSE with NaN filtering."""
    sim_vals = sim[sim_col].to_numpy(float)
    lab_vals = v3[v3_col].to_numpy(float)
    n = min(len(sim_vals), len(lab_vals))
    sim_vals = sim_vals[:n]
    lab_vals = lab_vals[:n]
    valid = ~np.isnan(lab_vals)
    if not np.any(valid):
        return 0.0
    sim_v = sim_vals[valid]
    lab_v = lab_vals[valid]
    diff = sim_v - lab_v
    rmse = float(np.sqrt(np.mean(diff ** 2)))
    lab_mean = float(np.mean(lab_v))
    nrmse = (rmse / lab_mean) * 100 if lab_mean > 1e-10 else 0.0
    return nrmse


def main():
    print("=" * 80, flush=True)
    print("R129y: Y_NX/Y_NP 逐批扫描（NH3_offline 改善）", flush=True)
    print("=" * 80, flush=True)

    y_nx_vals = [5, 8, 10, 12, 15, 20, 25, 30]
    y_np_vals = [40, 60, 80, 100, 120]

    results = {}
    best_per_batch = {}
    nh3_nrmses = []

    for b in GOLDEN:
        v3 = pd.read_csv(f"data/processed/batches/batch_{b:02d}.csv")
        cp = COMBINED[b]

        best_y_nx = 10
        best_y_np = 80
        best_nrmse = float('inf')
        best_yield = 0.0

        for y_nx in y_nx_vals:
            for y_np in y_np_vals:
                params = build_params(cp, y_nx, y_np)
                try:
                    sim, _ = simulate_open_loop(b, params)
                except Exception as e:
                    continue

                nh3_n = compute_channel_nrmse(sim, v3, "NH3", "NH3_offline")
                ym = yield_metrics(sim, v3)
                yield_err = ym["rel_err_total"]

                # Y_NX/Y_NP are dormant — yield should be unchanged
                if nh3_n < best_nrmse:
                    best_nrmse = nh3_n
                    best_y_nx = y_nx
                    best_y_np = y_np
                    best_yield = yield_err

        best_per_batch[b] = {"Y_NX": best_y_nx, "Y_NP": best_y_np,
                              "nh3_nrmse": best_nrmse, "yield_err": best_yield}
        nh3_nrmses.append(best_nrmse)

        print("  Batch {:2d}: best Y_NX={} Y_NP={} NH3={:.1f}% yield={:+.4f}".format(
            b, best_y_nx, best_y_np, best_nrmse, best_yield), flush=True)

    print("\n" + "-" * 80, flush=True)
    print("  Avg NH3: {:.1f}% (baseline 9.2%)".format(np.mean(nh3_nrmses)), flush=True)

    dst = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "runs", "p3", "d9_y_nx_y_np_calibration.json")
    with open(dst, "w", encoding="utf-8") as f:
        json.dump({"per_batch_best": {str(k): v for k, v in best_per_batch.items()}},
                  f, ensure_ascii=False, indent=2)
    print("\nSaved: %s" % dst, flush=True)


if __name__ == "__main__":
    main()

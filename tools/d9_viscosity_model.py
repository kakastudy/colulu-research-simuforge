# -*- coding: utf-8 -*-
"""R129r: 黏度模型改进——viscosity ≈ f(total_X)。

当前模型: dy[9] = 3*a_0^(1/3)*sigmoid1*sigmoid2 - k3*Fw
黏度与总菌体量相关性 0.81-0.85。尝试线性/幂律拟合。
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))

import numpy as np
import pandas as pd

from simulate import simulate_open_loop


COMBINED = {
    8:  {"mux": 0.47, "mup": 0.041, "dist_tcin_asym": 10, "m_s": 0.029,
          "biomass_death_rate": 0.001, "death_start": 100},
    22: {"mux": 0.35, "mup": 0.065, "dist_tcin_asym": 20, "m_s": 0.029,
          "m_s_schedule": [(110, 0.010)]},
    60: {"mux": 0.47, "mup": 0.035, "dist_tcin_asym": 15, "m_s": 0.010},
    91: {"mux": 0.39, "mup": 0.041, "dist_tcin_asym": 10, "m_s": 0.029,
          "biomass_death_rate": 0.005, "death_start": 200},
}


def main():
    print("=" * 80, flush=True)
    print("R129r: 黏度模型改进——viscosity ≈ f(total_X)", flush=True)
    print("=" * 80, flush=True)

    all_data = []
    for b in [8, 22, 60, 91]:
        v3 = pd.read_csv(f"data/processed/batches/batch_{b:02d}.csv")
        cp = COMBINED[b]
        params = {"mux": cp["mux"], "mup": cp["mup"], "alpha_kla": 85.0,
                  "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0,
                  "dist_flag": 1, "dist_tcin_asym": cp["dist_tcin_asym"], "m_s": cp["m_s"]}
        if "m_s_schedule" in cp:
            params["m_s_schedule"] = cp["m_s_schedule"]
        if "biomass_death_rate" in cp:
            params["biomass_death_rate"] = cp["biomass_death_rate"]
            params["death_start"] = cp["death_start"]

        sim, _ = simulate_open_loop(b, params)
        n = min(len(v3), len(sim))

        v3_vis = v3['Viscosity_offline'][:n].to_numpy(float)
        sim_vis = sim['vis'][:n].to_numpy(float)
        total_x = (sim['A0'][:n] + sim['A1'][:n] + sim['A3'][:n] + sim['A4'][:n]).to_numpy(float)

        valid = ~np.isnan(v3_vis)
        v3_vis_v = v3_vis[valid]
        sim_vis_v = sim_vis[valid]
        total_x_v = total_x[valid]

        print("\n  Batch {:2d}: sim_vis mean={:.2f} V3_vis mean={:.2f} | "
              "ratio={:.4f} | X mean={:.2f}".format(
                  b, np.mean(sim_vis_v), np.mean(v3_vis_v),
                  np.mean(sim_vis_v) / np.mean(v3_vis_v), np.mean(total_x_v)), flush=True)

        all_data.append((b, v3_vis_v, sim_vis_v, total_x_v))

    # Fit linear: V3_vis = a * total_X + b
    all_v3 = np.concatenate([d[1] for d in all_data])
    all_x = np.concatenate([d[3] for d in all_data])
    A = np.vstack([all_x, np.ones(len(all_x))]).T
    a_fit, b_fit = np.linalg.lstsq(A, all_v3, rcond=None)[0]
    pred_linear = a_fit * all_x + b_fit
    rmse_linear = float(np.sqrt(np.mean((pred_linear - all_v3) ** 2)))
    nrmse_linear = rmse_linear / np.mean(all_v3) * 100

    print("\n  Linear fit: V3_vis = {:.6f}*X + {:.4f}".format(a_fit, b_fit), flush=True)
    print("  nRMSE={:.1f}% (vs current model nRMSE=42.9%)".format(nrmse_linear), flush=True)

    # Fit power law: V3_vis = c * X^d
    log_x = np.log(all_x)
    log_v = np.log(all_v3)
    A2 = np.vstack([log_x, np.ones(len(log_x))]).T
    d_fit, log_c = np.linalg.lstsq(A2, log_v, rcond=None)[0]
    c_fit = np.exp(log_c)
    pred_power = c_fit * all_x ** d_fit
    rmse_power = float(np.sqrt(np.mean((pred_power - all_v3) ** 2)))
    nrmse_power = rmse_power / np.mean(all_v3) * 100

    print("  Power fit: V3_vis = {:.6f} * X^{:.4f}".format(c_fit, d_fit), flush=True)
    print("  nRMSE={:.1f}%".format(nrmse_power), flush=True)

    # Check current model nRMSE
    all_sim_vis = np.concatenate([d[2] for d in all_data])
    rmse_current = float(np.sqrt(np.mean((all_sim_vis - all_v3) ** 2)))
    nrmse_current = rmse_current / np.mean(all_v3) * 100
    print("  Current model nRMSE={:.1f}%".format(nrmse_current), flush=True)

    # Per-batch power fit
    print("\n  Per-batch power fit:", flush=True)
    for b, v3_v, sim_v, x_v in all_data:
        log_x = np.log(x_v)
        log_v = np.log(v3_v)
        A3 = np.vstack([log_x, np.ones(len(log_x))]).T
        d_b, log_c_b = np.linalg.lstsq(A3, log_v, rcond=None)[0]
        c_b = np.exp(log_c_b)
        pred_b = c_b * x_v ** d_b
        rmse_b = float(np.sqrt(np.mean((pred_b - v3_v) ** 2)))
        nrmse_b = rmse_b / np.mean(v3_v) * 100
        print("    Batch {:2d}: V3_vis = {:.4f} * X^{:.4f} nRMSE={:.1f}%".format(
            b, c_b, d_b, nrmse_b), flush=True)


if __name__ == "__main__":
    main()

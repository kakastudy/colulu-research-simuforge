# -*- coding: utf-8 -*-
"""R129p3: Q 通道线性回归校正——V3_Q = a * sim_Q + b。

逐时刻导数相关性 +0.96 表明 V3 Q 与 sim Q 动态一致但量级不同。
逐批线性回归校正验证。
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


def main():
    print("=" * 80, flush=True)
    print("R129p3: Q 通道线性回归校正", flush=True)
    print("=" * 80, flush=True)

    for b in GOLDEN:
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
        v3_q = v3['Q'].to_numpy(float)[:n]
        sim_q = sim['Q'].to_numpy(float)[:n]

        # Linear regression: V3_Q = a * sim_Q + b
        A = np.vstack([sim_q, np.ones(len(sim_q))]).T
        a_fit, b_fit = np.linalg.lstsq(A, v3_q, rcond=None)[0]

        # Compute nRMSE before and after correction
        rmse_before = float(np.sqrt(np.mean((sim_q - v3_q) ** 2)))
        nrmse_before = rmse_before / np.mean(v3_q) * 100 if np.mean(v3_q) > 1e-10 else 0

        sim_q_corrected = a_fit * sim_q + b_fit
        rmse_after = float(np.sqrt(np.mean((sim_q_corrected - v3_q) ** 2)))
        nrmse_after = rmse_after / np.mean(v3_q) * 100 if np.mean(v3_q) > 1e-10 else 0

        print("  Batch {:2d}: a={:.6f} b={:.4f} | before nRMSE={:.1f}% after={:.1f}% | "
              "mean_V3={:.1f} mean_sim={:.1f}".format(
                  b, a_fit, b_fit, nrmse_before, nrmse_after, np.mean(v3_q), np.mean(sim_q)), flush=True)

    print("\nConclusion:", flush=True)
    print("  If after-nRMSE is low (<15%), Q channel can be fixed", flush=True)
    print("  by per-batch linear regression in D6 health view.", flush=True)


if __name__ == "__main__":
    main()

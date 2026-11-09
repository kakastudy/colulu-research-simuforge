# -*- coding: utf-8 -*-
"""R129q2: P 在线 vs 离线通道对比——8/12 critical 但 P_offline 12/12 healthy。"""
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
    print("R129q2: P 在线 vs 离线通道对比", flush=True)
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

        sim_p = sim['P'][:n].to_numpy(float)
        v3_p = v3['P'][:n].to_numpy(float)
        v3_p_off = v3['P_offline'][:n].to_numpy(float)

        rmse_on = float(np.sqrt(np.mean((sim_p - v3_p) ** 2)))
        nrmse_on = rmse_on / np.mean(v3_p) * 100 if np.mean(v3_p) > 1e-10 else 0

        rmse_off = float(np.sqrt(np.mean((sim_p - v3_p_off) ** 2)))
        nrmse_off = rmse_off / np.mean(v3_p_off) * 100 if np.mean(v3_p_off) > 1e-10 else 0

        # Check if P online is a filtered version of P offline
        # Compare V3 P vs V3 P_offline
        rmse_v3 = float(np.sqrt(np.mean((v3_p - v3_p_off) ** 2)))
        nrmse_v3 = rmse_v3 / np.mean(v3_p_off) * 100 if np.mean(v3_p_off) > 1e-10 else 0

        print("  Batch {:2d}: P_online nRMSE={:.1f}% P_offline nRMSE={:.1f}% | "
              "V3_P_vs_P_off nRMSE={:.1f}% | "
              "P_on mean={:.4f} P_off mean={:.4f}".format(
                  b, nrmse_on, nrmse_off, nrmse_v3, np.mean(v3_p), np.mean(v3_p_off)), flush=True)

    print("\nConclusion:", flush=True)
    print("  If V3_P vs V3_P_off nRMSE is high, the online P is", flush=True)
    print("  a noisy/filtered version of the offline P.", flush=True)
    print("  Sim P matches the offline P better than the online P.", flush=True)


if __name__ == "__main__":
    main()

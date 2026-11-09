# -*- coding: utf-8 -*-
"""R129p: Qcon 对照——检查 V3 Q 是否等于夹套冷却 Qcon。"""
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
    print("R129p: Qcon 对照——V3 Q vs Sim Qcon", flush=True)
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

        v3_q_mean = v3['Q'].mean()
        sim_q_mean = sim['Q'].mean()
        sim_qcon_mean = sim['Qcon'].mean()

        # Try: V3 Q = Qcon (jacket cooling only)
        ratio_qcon = sim_qcon_mean / v3_q_mean if v3_q_mean > 1e-10 else 0
        # Try: V3 Q = Q - Qcon (total heat flow minus jacket cooling)
        ratio_q_minus_qcon = (sim_q_mean - sim_qcon_mean) / v3_q_mean if v3_q_mean > 1e-10 else 0
        # Try: V3 Q = Q * scale (find best scale)
        best_scale = v3_q_mean / sim_q_mean if sim_q_mean > 1e-10 else 0

        print("  Batch {:2d}: V3_Q={:8.1f} Sim_Q={:8.1f} Sim_Qcon={:8.1f} | "
              "Qcon/V3={:.4f} (Q-Qcon)/V3={:.4f} V3/Sim={:.4f}".format(
                  b, v3_q_mean, sim_q_mean, sim_qcon_mean,
                  ratio_qcon, ratio_q_minus_qcon, best_scale), flush=True)

    print("\nConclusion:", flush=True)
    print("  If Qcon/V3 ≈ 1, then V3 Q = jacket cooling only.", flush=True)
    print("  If (Q-Qcon)/V3 ≈ 1, then V3 Q = total heat flow minus jacket cooling.", flush=True)
    print("  If V3/Sim ≈ constant, then V3 Q = sim Q * scale.", flush=True)


if __name__ == "__main__":
    main()

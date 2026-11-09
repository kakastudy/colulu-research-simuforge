# -*- coding: utf-8 -*-
"""R129m: q_co2 扫描——改善 CO2outgas/CER 通道健康。

D6 健康视图（R129k）显示 CO2outgas 10/12 critical（avg nRMSE 27.1%）、
CER 10/12 critical（avg nRMSE 27.0%）。CO2 通道由 q_co2 (par[91]=0.1353)
控制。仿真系统性高估 CO2 ~12%（ratio 1.12）。

扫描 q_co2∈{0.100, 0.110, 0.120, 0.125, 0.1353, 0.140, 0.150}
对 12 黄金批的 CO2outgas 和 CER 通道 nRMSE。
注意：q_co2 是全局参数，扫描找最优全局值。
"""
import json
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


def compute_channel_nrmse(sim, v3, sim_col, v3_col):
    sim_vals = sim[sim_col].to_numpy(float)
    lab_vals = v3[v3_col].to_numpy(float)
    n = min(len(sim_vals), len(lab_vals))
    sim_vals = sim_vals[:n]
    lab_vals = lab_vals[:n]
    diff = sim_vals - lab_vals
    rmse = float(np.sqrt(np.mean(diff ** 2)))
    lab_mean = float(np.mean(lab_vals))
    nrmse = (rmse / lab_mean) * 100 if lab_mean > 1e-10 else 0.0
    return nrmse


def build_params(cp, q_co2=None):
    params = {"mux": cp["mux"], "mup": cp["mup"], "alpha_kla": 85.0,
              "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0,
              "dist_flag": 1, "dist_tcin_asym": cp["dist_tcin_asym"], "m_s": cp["m_s"]}
    if "m_s_schedule" in cp:
        params["m_s_schedule"] = cp["m_s_schedule"]
    if "biomass_death_rate" in cp:
        params["biomass_death_rate"] = cp["biomass_death_rate"]
        params["death_start"] = cp["death_start"]
    if q_co2 is not None:
        params["q_co2"] = q_co2
    return params


def main():
    print("=" * 80, flush=True)
    print("R129m: q_co2 扫描——改善 CO2outgas/CER 通道", flush=True)
    print("=" * 80, flush=True)

    q_co2_values = [0.100, 0.110, 0.120, 0.125, 0.1353, 0.140, 0.150]

    # Get all V3 data
    v3_data = {}
    for b in GOLDEN:
        v3_data[b] = pd.read_csv(f"data/processed/batches/batch_{b:02d}.csv")

    results = {}
    for q_co2 in q_co2_values:
        print(f"\nq_co2 = {q_co2:.4f}:", flush=True)
        co2_nrmses = []
        cer_nrmses = []
        for b in GOLDEN:
            cp = COMBINED[b]
            params = build_params(cp, q_co2)
            sim, _ = simulate_open_loop(b, params)
            co2_nrmse = compute_channel_nrmse(sim, v3_data[b], "CO2outgas", "CO2outgas")
            cer_nrmse = compute_channel_nrmse(sim, v3_data[b], "CER", "CER")
            co2_nrmses.append(co2_nrmse)
            cer_nrmses.append(cer_nrmse)
            if q_co2 == 0.1353:
                print("  Batch %2d: CO2=%.1f%% CER=%.1f%%" % (b, co2_nrmse, cer_nrmse), flush=True)

        avg_co2 = np.mean(co2_nrmses)
        avg_cer = np.mean(cer_nrmses)
        results[f"q_co2_{q_co2}"] = {
            "avg_co2_nrmse": round(avg_co2, 2),
            "avg_cer_nrmse": round(avg_cer, 2),
            "co2_nrmses": [round(x, 2) for x in co2_nrmses],
            "cer_nrmses": [round(x, 2) for x in cer_nrmses],
        }
        print("  Avg: CO2=%.1f%% CER=%.1f%%" % (avg_co2, avg_cer), flush=True)

    # Find best q_co2
    best_key = min(results.items(), key=lambda x: (x[1]["avg_co2_nrmse"] + x[1]["avg_cer_nrmse"]) / 2)
    print("\n" + "=" * 80, flush=True)
    print("BEST: %s → avg CO2=%.1f%% CER=%.1f%%" % (
        best_key[0], best_key[1]["avg_co2_nrmse"], best_key[1]["avg_cer_nrmse"]), flush=True)
    print("Baseline (q_co2=0.1353): avg CO2=%.1f%% CER=%.1f%%" % (
        results["q_co2_0.1353"]["avg_co2_nrmse"], results["q_co2_0.1353"]["avg_cer_nrmse"]), flush=True)

    dst = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "runs", "p3", "d9_q_co2_sweep.json")
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("Saved: %s" % dst, flush=True)


if __name__ == "__main__":
    main()

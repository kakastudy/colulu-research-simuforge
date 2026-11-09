# -*- coding: utf-8 -*-
"""R129v2: q_co2=0.120 全黄金批验证——改善 CO2 通道，检查产量。

R129m 结论（q_co2 影响产量通过 CO2 抑制）错误。
实际只有 q_co2=0.110 触发数值不稳定（批 91 yield -29.8%），
q_co2=0.100/0.120/0.1353/0.140 均正常（yield ≈ +4.4%）。
CO2 抑制在 10/12 批未激活（inhib_frac=0%），2 批短暂激活（<4%）。
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


def build_params(cp, q_co2=0.1353):
    params = {"mux": cp["mux"], "mup": cp["mup"], "alpha_kla": 85.0,
              "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0,
              "dist_flag": 1, "dist_tcin_asym": cp["dist_tcin_asym"], "m_s": cp["m_s"],
              "q_co2": q_co2}
    if "m_s_schedule" in cp:
        params["m_s_schedule"] = cp["m_s_schedule"]
    if "biomass_death_rate" in cp:
        params["biomass_death_rate"] = cp["biomass_death_rate"]
        params["death_start"] = cp["death_start"]
    return params


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


def main():
    print("=" * 80, flush=True)
    print("R129v2: q_co2=0.120 全黄金批验证", flush=True)
    print("=" * 80, flush=True)

    results = {}
    co2_nrmses_120 = []
    co2_nrmses_1353 = []
    cer_nrmses_120 = []
    cer_nrmses_1353 = []
    yield_errs_120 = []
    yield_errs_1353 = []

    for b in GOLDEN:
        v3 = pd.read_csv(f"data/processed/batches/batch_{b:02d}.csv")
        cp = COMBINED[b]

        # q_co2 = 0.1353 (baseline)
        sim_base, _ = simulate_open_loop(b, build_params(cp, 0.1353))
        co2_base = compute_channel_nrmse(sim_base, v3, "CO2outgas", "CO2outgas")
        cer_base = compute_channel_nrmse(sim_base, v3, "CER", "CER")
        ym_base = yield_metrics(sim_base, v3)
        yield_base = ym_base["rel_err_total"]

        # q_co2 = 0.120
        sim_new, _ = simulate_open_loop(b, build_params(cp, 0.120))
        co2_new = compute_channel_nrmse(sim_new, v3, "CO2outgas", "CO2outgas")
        cer_new = compute_channel_nrmse(sim_new, v3, "CER", "CER")
        ym_new = yield_metrics(sim_new, v3)
        yield_new = ym_new["rel_err_total"]

        co2_nrmses_1353.append(co2_base)
        co2_nrmses_120.append(co2_new)
        cer_nrmses_1353.append(cer_base)
        cer_nrmses_120.append(cer_new)
        yield_errs_1353.append(yield_base)
        yield_errs_120.append(yield_new)

        results[str(b)] = {
            "co2_nrmse_1353": round(co2_base, 2),
            "co2_nrmse_120": round(co2_new, 2),
            "cer_nrmse_1353": round(cer_base, 2),
            "cer_nrmse_120": round(cer_new, 2),
            "yield_1353": round(yield_base, 4),
            "yield_120": round(yield_new, 4),
        }

        print("  Batch {:2d}: CO2 {:.1f}%→{:.1f}% | CER {:.1f}%→{:.1f}% | "
              "yield {:+.4f}→{:+.4f}".format(
                  b, co2_base, co2_new, cer_base, cer_new, yield_base, yield_new), flush=True)

    print("\n" + "-" * 80, flush=True)
    avg_co2_1353 = np.mean(co2_nrmses_1353)
    avg_co2_120 = np.mean(co2_nrmses_120)
    avg_cer_1353 = np.mean(cer_nrmses_1353)
    avg_cer_120 = np.mean(cer_nrmses_120)
    rmse_yield_1353 = float(np.sqrt(np.mean([e ** 2 for e in yield_errs_1353])))
    rmse_yield_120 = float(np.sqrt(np.mean([e ** 2 for e in yield_errs_120])))

    print("  Avg CO2:  {:.1f}% → {:.1f}% ({:.1f}% improvement)".format(
        avg_co2_1353, avg_co2_120, (1 - avg_co2_120 / avg_co2_1353) * 100), flush=True)
    print("  Avg CER:  {:.1f}% → {:.1f}% ({:.1f}% improvement)".format(
        avg_cer_1353, avg_cer_120, (1 - avg_cer_120 / avg_cer_1353) * 100), flush=True)
    print("  RMSE yield: {:.4f} → {:.4f}".format(rmse_yield_1353, rmse_yield_120), flush=True)

    dst = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "runs", "p3", "d9_q_co2_0120_validation.json")
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("\nSaved: %s" % dst, flush=True)


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""R129w2: q_co2 逐批校准（产量约束版）——改善 CO2/CER/OUR 通道。

R129w 发现：批 60 q_co2=0.15 → yield -92.5%（CO2 抑制激活 3.7%）；
批 91 q_co2=0.11 → yield -29.8%（数值不稳定）。
约束：只考虑 |yield_err| < 5% 的 q_co2 值。
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


def build_params(cp, q_co2=0.120):
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
    print("R129w2: q_co2 逐批校准（产量约束 |yield_err|<5%）", flush=True)
    print("=" * 80, flush=True)

    q_co2s = [0.080, 0.090, 0.100, 0.110, 0.120, 0.130, 0.140, 0.150]
    results = {}
    best_qc_per_batch = {}
    co2_nrmses = []
    cer_nrmses = []
    our_nrmses = []
    yield_errs = []

    for b in GOLDEN:
        v3 = pd.read_csv(f"data/processed/batches/batch_{b:02d}.csv")
        cp = COMBINED[b]

        best_qc = 0.120
        best_co2_nrmse = float('inf')
        safe_qcs = []

        for qc in q_co2s:
            params = build_params(cp, qc)
            try:
                sim, _ = simulate_open_loop(b, params)
            except Exception as e:
                print("  Batch {:2d} q_co2={}: ERROR {}".format(b, qc, e), flush=True)
                continue

            co2_n = compute_channel_nrmse(sim, v3, "CO2outgas", "CO2outgas")
            cer_n = compute_channel_nrmse(sim, v3, "CER", "CER")
            our_n = compute_channel_nrmse(sim, v3, "OUR", "OUR")
            ym = yield_metrics(sim, v3)
            yield_err = ym["rel_err_total"]

            results.setdefault(str(b), {})[str(qc)] = {
                "co2_nrmse": round(co2_n, 2),
                "cer_nrmse": round(cer_n, 2),
                "our_nrmse": round(our_n, 2),
                "yield_err": round(yield_err, 4),
            }

            # Only consider q_co2 values that don't break yield
            if abs(yield_err) < 0.05:
                safe_qcs.append((qc, co2_n, cer_n, our_n, yield_err))

        # Pick best safe q_co2
        if safe_qcs:
            safe_qcs.sort(key=lambda x: x[1])  # sort by CO2 nRMSE
            best_qc, best_co2, best_cer, best_our, best_ye = safe_qcs[0]
            best_qc_per_batch[b] = {"q_co2": best_qc, "co2_nrmse": best_co2,
                                    "cer_nrmse": best_cer, "our_nrmse": best_our,
                                    "yield_err": best_ye}
        else:
            best_qc = 0.120
            best_co2 = compute_channel_nrmse(simulate_open_loop(b, build_params(cp, 0.120))[0], v3, "CO2outgas", "CO2outgas")
            best_cer = compute_channel_nrmse(simulate_open_loop(b, build_params(cp, 0.120))[0], v3, "CER", "CER")
            best_our = compute_channel_nrmse(simulate_open_loop(b, build_params(cp, 0.120))[0], v3, "OUR", "OUR")
            ym = yield_metrics(simulate_open_loop(b, build_params(cp, 0.120))[0], v3)
            best_ye = ym["rel_err_total"]
            best_qc_per_batch[b] = {"q_co2": best_qc, "co2_nrmse": best_co2,
                                    "cer_nrmse": best_cer, "our_nrmse": best_our,
                                    "yield_err": best_ye}
            print("  Batch {:2d}: NO SAFE q_co2! Using default 0.120".format(b), flush=True)

        co2_nrmses.append(best_co2)
        cer_nrmses.append(best_cer)
        our_nrmses.append(best_our)
        yield_errs.append(best_ye)

        print("  Batch {:2d}: best_q_co2={} CO2={:.1f}% CER={:.1f}% OUR={:.1f}% yield={:+.4f} safe={}".format(
            b, best_qc, best_co2, best_cer, best_our, best_ye, len(safe_qcs) > 0), flush=True)

    print("\n" + "-" * 80, flush=True)
    print("  Avg CO2: {:.1f}% | Avg CER: {:.1f}% | Avg OUR: {:.1f}%".format(
        np.mean(co2_nrmses), np.mean(cer_nrmses), np.mean(our_nrmses)), flush=True)
    rmse_yield = float(np.sqrt(np.mean([e ** 2 for e in yield_errs])))
    print("  RMSE yield: {:.4f}".format(rmse_yield), flush=True)

    dst = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "runs", "p3", "d9_q_co2_perbatch_constrained.json")
    with open(dst, "w", encoding="utf-8") as f:
        json.dump({"per_batch_best": {str(k): v for k, v in best_qc_per_batch.items()},
                   "detailed": results}, f, ensure_ascii=False, indent=2)
    print("\nSaved: %s" % dst, flush=True)


if __name__ == "__main__":
    main()

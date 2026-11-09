# -*- coding: utf-8 -*-
"""R129x2: N_conc_paa 逐批校准（NaN 过滤版）——改善 NH3_offline 通道。

R129x NaN bug：compute_channel_nrmse 不过滤 NaN → 稀疏 offline 通道返回 0.0%（假阳性）。
修正：过滤 NaN 后计算 nRMSE。
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


def build_params(cp, n_conc_paa=150000.0):
    params = {"mux": cp["mux"], "mup": cp["mup"], "alpha_kla": 85.0,
              "PAA_c": 530000.0, "N_conc_paa": n_conc_paa, "c_oil": 1000.0,
              "dist_flag": 1, "dist_tcin_asym": cp["dist_tcin_asym"], "m_s": cp["m_s"],
              "q_co2": cp["q_co2"]}
    if "m_s_schedule" in cp:
        params["m_s_schedule"] = cp["m_s_schedule"]
    if "biomass_death_rate" in cp:
        params["biomass_death_rate"] = cp["biomass_death_rate"]
        params["death_start"] = cp["death_start"]
    return params


def compute_channel_nrmse(sim, v3, sim_col, v3_col):
    """Compute nRMSE with NaN filtering (R129q2 fix)."""
    sim_vals = sim[sim_col].to_numpy(float)
    lab_vals = v3[v3_col].to_numpy(float)
    n = min(len(sim_vals), len(lab_vals))
    sim_vals = sim_vals[:n]
    lab_vals = lab_vals[:n]
    valid = ~np.isnan(lab_vals)
    if not np.any(valid):
        return 0.0  # no data
    sim_v = sim_vals[valid]
    lab_v = lab_vals[valid]
    diff = sim_v - lab_v
    rmse = float(np.sqrt(np.mean(diff ** 2)))
    lab_mean = float(np.mean(lab_v))
    nrmse = (rmse / lab_mean) * 100 if lab_mean > 1e-10 else 0.0
    return nrmse


def main():
    print("=" * 80, flush=True)
    print("R129x2: N_conc_paa 逐批扫描（NaN 过滤版）", flush=True)
    print("=" * 80, flush=True)

    n_concs = [80000, 100000, 120000, 150000, 200000, 250000, 300000]
    results = {}
    best_ncp_per_batch = {}
    nh3_nrmses = []
    yield_errs = []

    for b in GOLDEN:
        v3 = pd.read_csv(f"data/processed/batches/batch_{b:02d}.csv")
        cp = COMBINED[b]

        best_ncp = 150000.0
        best_nrmse = float('inf')
        best_yield = 0.0

        for ncp in n_concs:
            params = build_params(cp, ncp)
            try:
                sim, _ = simulate_open_loop(b, params)
            except Exception as e:
                print("  Batch {:2d} N_conc_paa={}: ERROR {}".format(b, ncp, e), flush=True)
                continue

            nh3_n = compute_channel_nrmse(sim, v3, "NH3", "NH3_offline")
            ym = yield_metrics(sim, v3)
            yield_err = ym["rel_err_total"]

            results.setdefault(str(b), {})[str(ncp)] = {
                "nh3_nrmse": round(nh3_n, 2),
                "yield_err": round(yield_err, 4),
            }

            if abs(yield_err) < 0.05 and nh3_n < best_nrmse:
                best_nrmse = nh3_n
                best_ncp = ncp
                best_yield = yield_err

        best_ncp_per_batch[b] = {"n_conc_paa": best_ncp, "nh3_nrmse": best_nrmse,
                                  "yield_err": best_yield}

        nh3_nrmses.append(best_nrmse)
        yield_errs.append(best_yield)

        print("  Batch {:2d}: best_N_conc_paa={} NH3={:.1f}% yield={:+.4f}".format(
            b, best_ncp, best_nrmse, best_yield), flush=True)

    print("\n" + "-" * 80, flush=True)
    print("  Avg NH3: {:.1f}%".format(np.mean(nh3_nrmses)), flush=True)
    rmse_yield = float(np.sqrt(np.mean([e ** 2 for e in yield_errs])))
    print("  RMSE yield: {:.4f}".format(rmse_yield), flush=True)

    dst = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "runs", "p3", "d9_nconc_paa_calibration_v2.json")
    with open(dst, "w", encoding="utf-8") as f:
        json.dump({"per_batch_best": {str(k): v for k, v in best_ncp_per_batch.items()},
                   "detailed": results}, f, ensure_ascii=False, indent=2)
    print("\nSaved: %s" % dst, flush=True)


if __name__ == "__main__":
    main()

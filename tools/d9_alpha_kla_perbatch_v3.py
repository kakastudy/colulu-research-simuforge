# -*- coding: utf-8 -*-
"""R129z2: Verify alpha_kla per-batch with COMBINED dict params (not calib_params).

The calib_params function has biomass_death_rate/death_start mismatches with COMBINED dict.
This script uses COMBINED dict params directly to get accurate alpha_kla results.
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
          "biomass_death_rate": 0.001, "death_start": 100, "q_co2": 0.12, "Y_NX": 10, "Y_NP": 80},
    11: {"mux": 0.41, "mup": 0.041, "dist_tcin_asym": 10, "m_s": 0.020, "q_co2": 0.11, "Y_NX": 10, "Y_NP": 80},
    16: {"mux": 0.41, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.025,
          "biomass_death_rate": 0.005, "death_start": 0, "q_co2": 0.14, "Y_NX": 25, "Y_NP": 40},
    22: {"mux": 0.35, "mup": 0.065, "dist_tcin_asym": 20, "m_s": 0.029,
          "m_s_schedule": [(110, 0.010)], "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40},
    23: {"mux": 0.35, "mup": 0.070, "dist_tcin_asym": 10, "m_s": 0.029,
          "biomass_death_rate": 0.0005, "death_start": 200, "q_co2": 0.10, "Y_NX": 15, "Y_NP": 60},
    27: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 15, "m_s": 0.029,
          "m_s_schedule": [(140, 0.018)], "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40},
    36: {"mux": 0.47, "mup": 0.045, "dist_tcin_asym": 10, "m_s": 0.010, "q_co2": 0.10, "Y_NX": 20, "Y_NP": 40},
    55: {"mux": 0.47, "mup": 0.055, "dist_tcin_asym": 20, "m_s": 0.025,
          "biomass_death_rate": 0.001, "death_start": 200, "q_co2": 0.11, "Y_NX": 25, "Y_NP": 40},
    60: {"mux": 0.47, "mup": 0.035, "dist_tcin_asym": 15, "m_s": 0.010, "q_co2": 0.10, "Y_NX": 20, "Y_NP": 40},
    80: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 18, "m_s": 0.029,
          "biomass_death_rate": 0.005, "death_start": 0, "q_co2": 0.13, "Y_NX": 25, "Y_NP": 40},
    91: {"mux": 0.39, "mup": 0.041, "dist_tcin_asym": 10, "m_s": 0.029,
          "biomass_death_rate": 0.005, "death_start": 200, "q_co2": 0.12, "Y_NX": 10, "Y_NP": 60},
    92: {"mux": 0.47, "mup": 0.041, "dist_tcin_asym": 18, "m_s": 0.029,
          "m_s_schedule": [(150, 0.015)],
          "biomass_death_rate": 0.005, "death_start": 200, "q_co2": 0.11, "Y_NX": 12, "Y_NP": 60},
}

GOLDEN = [8, 11, 16, 22, 23, 27, 36, 55, 60, 80, 91, 92]


def build_params(cp, alpha_kla=85.0):
    params = {"mux": cp["mux"], "mup": cp["mup"], "alpha_kla": alpha_kla,
              "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0,
              "dist_flag": 1, "dist_tcin_asym": cp["dist_tcin_asym"], "m_s": cp["m_s"],
              "q_co2": cp["q_co2"], "Y_NX": cp["Y_NX"], "Y_NP": cp["Y_NP"]}
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
    print("R129z2: alpha_kla 逐批扫描（COMBINED dict 参数）", flush=True)
    print("=" * 80, flush=True)

    alpha_klas = [60, 70, 75, 80, 85, 90, 95, 100, 105, 110, 120, 130]

    results = {}
    best_per_batch = {}
    do2_nrmses = []
    o2_nrmses = []
    co2_nrmses = []
    yield_errs = []

    for b in GOLDEN:
        v3 = pd.read_csv(f"data/processed/batches/batch_{b:02d}.csv")
        cp = COMBINED[b]

        best_ak = 85.0
        best_do2 = float('inf')
        best_o2 = 0.0
        best_yield = 0.0
        best_co2 = 0.0

        for ak in alpha_klas:
            params = build_params(cp, ak)
            try:
                sim, _ = simulate_open_loop(b, params)
            except Exception as e:
                print("  Batch {:2d} alpha_kla={}: ERROR {}".format(b, ak, e), flush=True)
                continue

            do2_n = compute_channel_nrmse(sim, v3, "DO2", "DO2")
            o2_n = compute_channel_nrmse(sim, v3, "O2", "O2")
            co2_n = compute_channel_nrmse(sim, v3, "CO2outgas", "CO2outgas")
            ym = yield_metrics(sim, v3)
            yield_err = ym["rel_err_total"]

            results.setdefault(str(b), {})[str(ak)] = {
                "do2_nrmse": round(do2_n, 2),
                "o2_nrmse": round(o2_n, 2),
                "co2_nrmse": round(co2_n, 2),
                "yield_err": round(yield_err, 4),
            }

            # Only consider if yield is safe AND O2 stays reasonable
            if abs(yield_err) < 0.05 and o2_n < 10.0 and do2_n < best_do2:
                best_do2 = do2_n
                best_ak = ak
                best_o2 = o2_n
                best_yield = yield_err
                best_co2 = co2_n

        best_per_batch[b] = {"alpha_kla": best_ak, "do2_nrmse": best_do2,
                              "o2_nrmse": best_o2, "yield_err": best_yield,
                              "co2_nrmse": best_co2}
        do2_nrmses.append(best_do2)
        o2_nrmses.append(best_o2)
        co2_nrmses.append(best_co2)
        yield_errs.append(best_yield)

        print("  Batch {:2d}: best_ak={} DO2={:.1f}% O2={:.1f}% CO2={:.1f}% yield={:+.4f}".format(
            b, best_ak, best_do2, best_o2, best_co2, best_yield), flush=True)

    print("\n" + "-" * 80, flush=True)
    print("  Avg DO2: {:.1f}% (baseline 18.3%)".format(np.mean(do2_nrmses)), flush=True)
    print("  Avg O2:  {:.1f}% (baseline 2.2%)".format(np.mean(o2_nrmses)), flush=True)
    print("  Avg CO2: {:.1f}% (baseline 15.2%)".format(np.mean(co2_nrmses)), flush=True)
    rmse_yield = float(np.sqrt(np.mean([e ** 2 for e in yield_errs])))
    print("  RMSE yield: {:.4f}".format(rmse_yield), flush=True)

    dst = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "runs", "p3", "d9_alpha_kla_perbatch_v3.json")
    with open(dst, "w", encoding="utf-8") as f:
        json.dump({"per_batch_best": {str(k): v for k, v in best_per_batch.items()},
                   "detailed": results}, f, ensure_ascii=False, indent=2)
    print("\nSaved: %s" % dst, flush=True)


if __name__ == "__main__":
    main()

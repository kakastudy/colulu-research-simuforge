# -*- coding: utf-8 -*-
"""R129ae: PAA_c + m_paa 2D sweep v2 — with PAA_CAL params (paa_degrad_rate,
paa_maintenance_target) as base, extended m_paa range.

Key insight: COMBINED dict (golden regression) does NOT include PAA_CAL params.
PAA_CAL has paa_degrad_rate and paa_maintenance_target that affect only the PAA ODE.
These are dormant (don't affect yield) when PAA stays in safe range.

v2 adds PAA_CAL's paa_degrad_rate and paa_maintenance_target as base params,
then sweeps PAA_c and m_paa with extended range (includes default 1.05).
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
          "biomass_death_rate": 0.001, "death_start": 100, "q_co2": 0.12, "Y_NX": 10, "Y_NP": 80, "alpha_kla": 90, "vis_scale": 0.9},
    11: {"mux": 0.41, "mup": 0.041, "dist_tcin_asym": 10, "m_s": 0.020, "q_co2": 0.11, "Y_NX": 10, "Y_NP": 80, "alpha_kla": 110, "vis_scale": 0.9},
    16: {"mux": 0.41, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.025,
          "biomass_death_rate": 0.005, "death_start": 0, "q_co2": 0.14, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 75, "vis_scale": 0.9},
    22: {"mux": 0.35, "mup": 0.065, "dist_tcin_asym": 20, "m_s": 0.029,
          "m_s_schedule": [(110, 0.010)], "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},
    23: {"mux": 0.35, "mup": 0.070, "dist_tcin_asym": 10, "m_s": 0.029,
          "biomass_death_rate": 0.0005, "death_start": 200, "q_co2": 0.1, "Y_NX": 15, "Y_NP": 60, "alpha_kla": 110, "vis_scale": 0.9},
    27: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 15, "m_s": 0.029,
          "m_s_schedule": [(140, 0.018)], "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85, "vis_scale": 0.9},
    36: {"mux": 0.47, "mup": 0.045, "dist_tcin_asym": 10, "m_s": 0.010, "q_co2": 0.1, "Y_NX": 20, "Y_NP": 40, "alpha_kla": 130, "vis_scale": 0.8},
    55: {"mux": 0.47, "mup": 0.055, "dist_tcin_asym": 20, "m_s": 0.025,
          "biomass_death_rate": 0.001, "death_start": 200, "q_co2": 0.11, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},
    60: {"mux": 0.47, "mup": 0.035, "dist_tcin_asym": 15, "m_s": 0.010, "q_co2": 0.1, "Y_NX": 20, "Y_NP": 40, "alpha_kla": 85},
    80: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 18, "m_s": 0.029,
          "biomass_death_rate": 0.005, "death_start": 0, "q_co2": 0.13, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85, "vis_scale": 0.9},
    91: {"mux": 0.39, "mup": 0.041, "dist_tcin_asym": 10, "m_s": 0.029,
          "biomass_death_rate": 0.005, "death_start": 200, "q_co2": 0.12, "Y_NX": 10, "Y_NP": 60, "alpha_kla": 90},
    92: {"mux": 0.47, "mup": 0.041, "dist_tcin_asym": 18, "m_s": 0.029,
          "m_s_schedule": [(150, 0.015)],
          "biomass_death_rate": 0.005, "death_start": 200, "q_co2": 0.11, "Y_NX": 12, "Y_NP": 60, "alpha_kla": 130, "vis_scale": 0.9},
}

PAA_CAL = {
    8:  {"m_paa": 0.5,  "paa_degrad_rate": 0.008,  "paa_maintenance_target": 1},
    11: {"m_paa": 0.5,  "paa_degrad_rate": 0.008,  "paa_maintenance_target": 1},
    16: {"m_paa": 1.0,  "paa_degrad_rate": 0.008,  "paa_maintenance_target": 1},
    22: {"m_paa": 1.0,  "paa_degrad_rate": 0.010,  "paa_maintenance_target": 1},
    23: {"m_paa": 0.1,  "paa_degrad_rate": 0.003,  "paa_maintenance_target": 1},
    27: {"m_paa": 0.5,  "paa_degrad_rate": 0.008,  "paa_maintenance_target": 1},
    36: {"m_paa": 0.1,  "paa_degrad_rate": 0.003,  "paa_maintenance_target": 1},
    55: {"m_paa": 0.3,  "paa_degrad_rate": 0.003,  "paa_maintenance_target": 1},
    60: {"m_paa": 0.5,  "paa_degrad_rate": 0.0045, "paa_maintenance_target": 1},
    80: {"m_paa": 0.5,  "paa_degrad_rate": 0.0045, "paa_maintenance_target": 1},
    91: {"m_paa": 0.1,  "paa_degrad_rate": 0.003,  "paa_maintenance_target": 1},
    92: {"m_paa": 0.5,  "paa_degrad_rate": 0.003,  "paa_maintenance_target": 1},
}

GOLDEN = [8, 11, 16, 22, 23, 27, 36, 55, 60, 80, 91, 92]


def build_params(cp, paa_cal):
    params = {"mux": cp["mux"], "mup": cp["mup"], "alpha_kla": cp["alpha_kla"],
              "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0,
              "dist_flag": 1, "dist_tcin_asym": cp["dist_tcin_asym"], "m_s": cp["m_s"],
              "q_co2": cp["q_co2"], "Y_NX": cp["Y_NX"], "Y_NP": cp["Y_NP"],
              "paa_degrad_rate": paa_cal["paa_degrad_rate"],
              "paa_maintenance_target": paa_cal["paa_maintenance_target"]}
    if "vis_scale" in cp:
        params["vis_scale"] = cp["vis_scale"]
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
    print("R129ae: PAA_c + m_paa 2D sweep v2 (with PAA_CAL params, extended range)", flush=True)
    print("=" * 80, flush=True)

    paa_c_values = [300000, 400000, 530000, 600000, 700000]
    m_paa_values = [0.05, 0.1, 0.3, 0.5, 0.7, 1.0, 1.05, 1.2, 1.5]

    results = {}
    best_per_batch = {}
    paa_nrmses = []
    yield_errs = []

    for b in GOLDEN:
        v3 = pd.read_csv(f"data/processed/batches/batch_{b:02d}.csv")
        cp = COMBINED[b]
        paa_cal = PAA_CAL[b]
        base_params = build_params(cp, paa_cal)

        best_pc = 530000.0
        best_mp = 1.05
        best_paa = float('inf')
        best_yield = 0.0

        for pc in paa_c_values:
            for mp in m_paa_values:
                params = dict(base_params)
                params["PAA_c"] = pc
                params["m_paa"] = mp
                try:
                    sim, _ = simulate_open_loop(b, params)
                except Exception as e:
                    print("  Batch {:2d} PAA_c={} m_paa={}: ERROR {}".format(b, pc, mp, e), flush=True)
                    continue

                paa_n = compute_channel_nrmse(sim, v3, "PAA", "PAA_offline")
                ym = yield_metrics(sim, v3)
                yield_err = ym["rel_err_total"]

                results.setdefault(str(b), {})[f"{pc}_{mp}"] = {
                    "paa_nrmse": round(paa_n, 2),
                    "yield_err": round(yield_err, 4),
                }

                if abs(yield_err) < 0.05 and paa_n < best_paa:
                    best_paa = paa_n
                    best_pc = pc
                    best_mp = mp
                    best_yield = yield_err

        best_per_batch[b] = {"PAA_c": best_pc, "m_paa": best_mp, "paa_nrmse": best_paa,
                              "yield_err": best_yield}
        paa_nrmses.append(best_paa)
        yield_errs.append(best_yield)

        print("  Batch {:2d}: best_PAA_c={} m_paa={} PAA={:.1f}% yield={:+.4f}".format(
            b, best_pc, best_mp, best_paa, best_yield), flush=True)

    print("\n" + "-" * 80, flush=True)
    avg_paa = float(np.mean([x for x in paa_nrmses if x < float('inf')]))
    print("  Avg PAA (excl inf): {:.1f}% (baseline 42.6%)".format(avg_paa), flush=True)
    rmse_yield = float(np.sqrt(np.mean([e ** 2 for e in yield_errs])))
    print("  RMSE yield: {:.4f}".format(rmse_yield), flush=True)

    dst = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "runs", "p3", "d9_paa_c_mpaa_2d_v2.json")
    with open(dst, "w", encoding="utf-8") as f:
        json.dump({"per_batch_best": {str(k): v for k, v in best_per_batch.items()},
                   "detailed": results}, f, ensure_ascii=False, indent=2)
    print("\nSaved: %s" % dst, flush=True)


if __name__ == "__main__":
    main()

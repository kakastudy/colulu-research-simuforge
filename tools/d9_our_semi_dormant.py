# -*- coding: utf-8 -*-
"""R129ag: OUR channel semi-dormant probe — sweep Y_O2_X, Y_O2_P, m_O2_X.

OUR = -X_1 * Y_O2_X - m_O2_X * X_t - dP_dt * Y_O2_P
dy[1] = OUR + OTR - y[1] * dilution / y[4]  (O2 ODE)

These params affect both OUR channel AND O2 ODE. O2 is excellent (2.2%) —
maybe there's room for semi-dormant tuning (improve OUR while O2 stays < 5%).
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
          "biomass_death_rate": 0.001, "death_start": 100, "q_co2": 0.12, "Y_NX": 10, "Y_NP": 80, "alpha_kla": 90, "vis_scale": 0.9, "PAA_c": 530000.0, "m_paa": 1.0},
    11: {"mux": 0.41, "mup": 0.041, "dist_tcin_asym": 10, "m_s": 0.020, "q_co2": 0.11, "Y_NX": 10, "Y_NP": 80, "alpha_kla": 110, "vis_scale": 0.9, "PAA_c": 530000.0, "m_paa": 0.7},
    16: {"mux": 0.41, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.025,
          "biomass_death_rate": 0.005, "death_start": 0, "q_co2": 0.14, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 75, "vis_scale": 0.9, "PAA_c": 400000.0, "m_paa": 0.5},
    22: {"mux": 0.35, "mup": 0.065, "dist_tcin_asym": 20, "m_s": 0.029,
          "m_s_schedule": [(110, 0.010)], "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},
    23: {"mux": 0.35, "mup": 0.070, "dist_tcin_asym": 10, "m_s": 0.029,
          "biomass_death_rate": 0.0005, "death_start": 200, "q_co2": 0.1, "Y_NX": 15, "Y_NP": 60, "alpha_kla": 110, "vis_scale": 0.9, "PAA_c": 530000.0, "m_paa": 1.0},
    27: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 15, "m_s": 0.029,
          "m_s_schedule": [(140, 0.018)], "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85, "vis_scale": 0.9, "PAA_c": 530000.0, "m_paa": 1.0},
    36: {"mux": 0.47, "mup": 0.045, "dist_tcin_asym": 10, "m_s": 0.010, "q_co2": 0.1, "Y_NX": 20, "Y_NP": 40, "alpha_kla": 130, "vis_scale": 0.8, "PAA_c": 530000.0, "m_paa": 0.7},
    55: {"mux": 0.47, "mup": 0.055, "dist_tcin_asym": 20, "m_s": 0.025,
          "biomass_death_rate": 0.001, "death_start": 200, "q_co2": 0.11, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85, "PAA_c": 530000.0, "m_paa": 1.0},
    60: {"mux": 0.47, "mup": 0.035, "dist_tcin_asym": 15, "m_s": 0.010, "q_co2": 0.1, "Y_NX": 20, "Y_NP": 40, "alpha_kla": 85, "PAA_c": 530000.0, "m_paa": 1.0},
    80: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 18, "m_s": 0.029,
          "biomass_death_rate": 0.005, "death_start": 0, "q_co2": 0.13, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85, "vis_scale": 0.9, "PAA_c": 400000.0, "m_paa": 0.3},
    91: {"mux": 0.39, "mup": 0.041, "dist_tcin_asym": 10, "m_s": 0.029,
          "biomass_death_rate": 0.005, "death_start": 200, "q_co2": 0.12, "Y_NX": 10, "Y_NP": 60, "alpha_kla": 90},
    92: {"mux": 0.47, "mup": 0.041, "dist_tcin_asym": 18, "m_s": 0.029,
          "m_s_schedule": [(150, 0.015)],
          "biomass_death_rate": 0.005, "death_start": 200, "q_co2": 0.11, "Y_NX": 12, "Y_NP": 60, "alpha_kla": 130, "vis_scale": 0.9, "PAA_c": 530000.0, "m_paa": 0.7},
}

GOLDEN = [8, 11, 16, 22, 23, 27, 36, 55, 60, 80, 91, 92]


def build_params(cp):
    params = {"mux": cp["mux"], "mup": cp["mup"], "alpha_kla": cp["alpha_kla"],
              "PAA_c": cp.get("PAA_c", 530000.0), "N_conc_paa": 150000.0, "c_oil": 1000.0,
              "dist_flag": 1, "dist_tcin_asym": cp["dist_tcin_asym"], "m_s": cp["m_s"],
              "q_co2": cp["q_co2"], "Y_NX": cp["Y_NX"], "Y_NP": cp["Y_NP"]}
    if "m_paa" in cp:
        params["m_paa"] = cp["m_paa"]
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
    print("R129ag: OUR channel semi-dormant probe (Y_O2_X, Y_O2_P, m_O2_X sweep)", flush=True)
    print("=" * 80, flush=True)

    # Default values: Y_O2_X=650, Y_O2_P=160, m_O2_X=17.5
    y_o2_x_values = [400, 500, 650, 800, 1000]
    y_o2_p_values = [80, 120, 160, 200]
    m_o2_x_values = [10, 15, 17.5, 22]

    results = {}
    best_per_batch = {}
    our_nrmses = []
    o2_nrmses = []
    yield_errs = []

    for b in GOLDEN:
        v3 = pd.read_csv(f"data/processed/batches/batch_{b:02d}.csv")
        cp = COMBINED[b]
        base_params = build_params(cp)

        best_yox = 650.0
        best_yop = 160.0
        best_mox = 17.5
        best_our = float('inf')
        best_o2 = 0.0
        best_yield = 0.0

        for yox in y_o2_x_values:
            for yop in y_o2_p_values:
                for mox in m_o2_x_values:
                    params = dict(base_params)
                    params["Y_O2_X"] = yox
                    params["Y_O2_P"] = yop
                    params["m_O2_X"] = mox
                    try:
                        sim, _ = simulate_open_loop(b, params)
                    except Exception as e:
                        print("  Batch {:2d} Y_O2_X={} Y_O2_P={} m_O2_X={}: ERROR {}".format(b, yox, yop, mox, e), flush=True)
                        continue

                    our_n = compute_channel_nrmse(sim, v3, "OUR", "OUR")
                    o2_n = compute_channel_nrmse(sim, v3, "O2", "O2")
                    ym = yield_metrics(sim, v3)
                    yield_err = ym["rel_err_total"]

                    results.setdefault(str(b), {})[f"{yox}_{yop}_{mox}"] = {
                        "our_nrmse": round(our_n, 2),
                        "o2_nrmse": round(o2_n, 2),
                        "yield_err": round(yield_err, 4),
                    }

                    # Constraint: O2 must stay healthy (< 5%), yield within 5%
                    if o2_n < 5.0 and abs(yield_err) < 0.05 and our_n < best_our:
                        best_our = our_n
                        best_o2 = o2_n
                        best_yox = yox
                        best_yop = yop
                        best_mox = mox
                        best_yield = yield_err

        best_per_batch[b] = {"Y_O2_X": best_yox, "Y_O2_P": best_yop, "m_O2_X": best_mox,
                              "our_nrmse": best_our, "o2_nrmse": best_o2, "yield_err": best_yield}
        our_nrmses.append(best_our)
        o2_nrmses.append(best_o2)
        yield_errs.append(best_yield)

        print("  Batch {:2d}: best Y_O2_X={} Y_O2_P={} m_O2_X={} OUR={:.1f}% O2={:.2f}% yield={:+.4f}".format(
            b, best_yox, best_yop, best_mox, best_our, best_o2, best_yield), flush=True)

    print("\n" + "-" * 80, flush=True)
    avg_our = float(np.mean([x for x in our_nrmses if x < float('inf')]))
    print("  Avg OUR (excl inf): {:.1f}% (baseline 41.6%)".format(avg_our), flush=True)
    avg_o2 = float(np.mean(o2_nrmses))
    print("  Avg O2: {:.2f}% (baseline 2.2%)".format(avg_o2), flush=True)
    rmse_yield = float(np.sqrt(np.mean([e ** 2 for e in yield_errs])))
    print("  RMSE yield: {:.4f}".format(rmse_yield), flush=True)

    dst = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "runs", "p3", "d9_our_semi_dormant.json")
    with open(dst, "w", encoding="utf-8") as f:
        json.dump({"per_batch_best": {str(k): v for k, v in best_per_batch.items()},
                   "detailed": results}, f, ensure_ascii=False, indent=2)
    print("\nSaved: %s" % dst, flush=True)


if __name__ == "__main__":
    main()

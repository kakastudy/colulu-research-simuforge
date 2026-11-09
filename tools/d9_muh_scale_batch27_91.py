# -*- coding: utf-8 -*-
"""R129ai2: Sweep mu_h_scale on Batch 27 and 91 with correct dist_flag=1.

The previous sweep (d9_muh_scale_golden_sweep.py) didn't set dist_flag=1,
causing Batch 27/91 to crash (-100%). This version matches the golden
regression params construction exactly.
"""
import os
import sys
import json
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))

from simulate import simulate_open_loop, yield_metrics


def build_params(cp):
    """Build params dict matching diag_final_validation_v3.py exactly."""
    params = {"mux": cp["mux"], "mup": cp["mup"],
              "alpha_kla": cp.get("alpha_kla", 85.0),
              "PAA_c": cp.get("PAA_c", 530000.0), "N_conc_paa": 150000.0, "c_oil": 1000.0,
              "dist_flag": 1, "dist_tcin_asym": cp["dist_tcin_asym"], "m_s": cp["m_s"]}
    if "m_paa" in cp:
        params["m_paa"] = cp["m_paa"]
    if "m_s_schedule" in cp:
        params["m_s_schedule"] = cp["m_s_schedule"]
    if "biomass_death_rate" in cp:
        params["biomass_death_rate"] = cp["biomass_death_rate"]
        params["death_start"] = cp["death_start"]
    if "q_co2" in cp:
        params["q_co2"] = cp["q_co2"]
    if "Y_NX" in cp:
        params["Y_NX"] = cp["Y_NX"]
    if "Y_NP" in cp:
        params["Y_NP"] = cp["Y_NP"]
    if "vis_scale" in cp:
        params["vis_scale"] = cp["vis_scale"]
    if "Y_O2_X" in cp:
        params["Y_O2_X"] = cp["Y_O2_X"]
    if "Y_O2_P" in cp:
        params["Y_O2_P"] = cp["Y_O2_P"]
    if "m_O2_X" in cp:
        params["m_O2_X"] = cp["m_O2_X"]
    if "mu_h_scale" in cp:
        params["mu_h_scale"] = cp["mu_h_scale"]
    return params


# COMBINED dict params from diag_final_validation_v3.py
COMBINED = {
    27: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 15, "m_s": 0.029,
         "m_s_schedule": [(140, 0.018)], "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40,
         "alpha_kla": 85, "vis_scale": 0.9,
         "PAA_c": 530000.0, "m_paa": 1.0, "Y_O2_X": 650, "Y_O2_P": 160, "m_O2_X": 15},
    91: {"mux": 0.39, "mup": 0.041, "dist_tcin_asym": 10, "m_s": 0.029,
         "biomass_death_rate": 0.005, "death_start": 200,
         "q_co2": 0.12, "Y_NX": 10, "Y_NP": 60, "alpha_kla": 90},
}


def main():
    print("=" * 80, flush=True)
    print("R129ai2: mu_h_scale sweep on Batch 27 and 91 (with dist_flag=1)", flush=True)
    print("=" * 80, flush=True)

    all_results = {}

    for b in [27, 91]:
        v3 = pd.read_csv(f"data/processed/batches/batch_{b:02d}.csv")
        cp = COMBINED[b]
        base_params = build_params(cp)

        print("\n--- Batch {} ---".format(b), flush=True)

        # Baseline (no mu_h_scale)
        sim_base, _ = simulate_open_loop(b, base_params)
        ym_base = yield_metrics(sim_base, v3)
        base_err = ym_base["rel_err_total"]
        print("  Baseline: yield_err={:+.4f} ({:+.1f}%) P_final={:.1f}".format(
            base_err, base_err * 100, float(sim_base["P"].iloc[-1])), flush=True)

        # Sweep mu_h_scale
        best_err = base_err
        best_scale = 1.0
        results = []

        for scale in [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0, 6.0, 8.0, 10.0]:
            params = build_params(cp)
            params["mu_h_scale"] = scale
            try:
                sim, _ = simulate_open_loop(b, params)
                ym = yield_metrics(sim, v3)
                err = ym["rel_err_total"]
                p_final = float(sim["P"].iloc[-1])
                results.append({"mu_h_scale": scale, "yield_err": err, "p_final": p_final})
                if abs(err) < abs(best_err):
                    best_err = err
                    best_scale = scale
                marker = " ***" if abs(err) < 0.05 else ""
                print("  mu_h_scale={:.1f}: yield_err={:+.4f} ({:+.1f}%) P_final={:.1f}{}".format(
                    scale, err, err * 100, p_final, marker), flush=True)
            except Exception as e:
                print("  mu_h_scale={:.1f}: FAILED - {}".format(scale, str(e)[:50]), flush=True)

        print("\n  Best: mu_h_scale={} yield_err={:+.4f} ({:+.1f}%)".format(
            best_scale, best_err, best_err * 100), flush=True)

        all_results[b] = {"base_err": base_err, "best_scale": best_scale,
                          "best_err": best_err, "results": results}

    dst = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "runs", "p3", "d9_muh_scale_batch27_91.json")
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print("\nSaved: %s" % dst, flush=True)


if __name__ == "__main__":
    main()

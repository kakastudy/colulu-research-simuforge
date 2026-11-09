# -*- coding: utf-8 -*-
"""R129ai: Sweep mu_h_scale on remaining golden batches with yield errors.

Current golden set yield errors:
  Batch 27: +4.8%
  Batch 23: +4.4%
  Batch 91: +4.3%

mu_h_scale=3.5 fixed Batch 22 (+7.0%->-1.0%). Can it help these too?
"""
import os
import sys
import json
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))

from simulate import simulate_open_loop, yield_metrics


# COMBINED dict params from diag_final_validation_v3.py (without mu_h_scale)
COMBINED = {
    8: {"mux": 0.35, "mup": 0.045, "dist_tcin_asym": 15, "m_s": 0.029,
        "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 90, "vis_scale": 0.9,
        "PAA_c": 530000.0, "m_paa": 0.7, "Y_O2_X": 800, "Y_O2_P": 200, "m_O2_X": 15},
    11: {"mux": 0.41, "mup": 0.041, "dist_tcin_asym": 10, "m_s": 0.020,
         "q_co2": 0.11, "Y_NX": 10, "Y_NP": 80, "alpha_kla": 110, "vis_scale": 0.9,
         "PAA_c": 530000.0, "m_paa": 0.7, "Y_O2_X": 800, "Y_O2_P": 80, "m_O2_X": 15},
    16: {"mux": 0.41, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.025,
         "biomass_death_rate": 0.005, "death_start": 0,
         "q_co2": 0.14, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 75, "vis_scale": 0.9,
         "PAA_c": 400000.0, "m_paa": 0.5, "Y_O2_X": 800, "Y_O2_P": 200, "m_O2_X": 17.5},
    22: {"mux": 0.35, "mup": 0.065, "dist_tcin_asym": 20, "m_s": 0.029,
         "m_s_schedule": [(110, 0.010)], "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40,
         "alpha_kla": 85, "mu_h_scale": 3.5},
    23: {"mux": 0.35, "mup": 0.070, "dist_tcin_asym": 10, "m_s": 0.029,
         "biomass_death_rate": 0.0005, "death_start": 200,
         "q_co2": 0.1, "Y_NX": 15, "Y_NP": 60, "alpha_kla": 110, "vis_scale": 0.9,
         "PAA_c": 530000.0, "m_paa": 1.0, "Y_O2_X": 650, "Y_O2_P": 200, "m_O2_X": 15},
    27: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 15, "m_s": 0.029,
         "m_s_schedule": [(140, 0.018)], "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40,
         "alpha_kla": 85, "vis_scale": 0.9,
         "PAA_c": 530000.0, "m_paa": 1.0, "Y_O2_X": 650, "Y_O2_P": 160, "m_O2_X": 15},
    36: {"mux": 0.47, "mup": 0.045, "dist_tcin_asym": 10, "m_s": 0.010,
         "q_co2": 0.1, "Y_NX": 20, "Y_NP": 40, "alpha_kla": 130, "vis_scale": 0.8,
         "PAA_c": 530000.0, "m_paa": 0.7, "Y_O2_X": 650, "Y_O2_P": 160, "m_O2_X": 10},
    55: {"mux": 0.47, "mup": 0.055, "dist_tcin_asym": 20, "m_s": 0.025,
         "biomass_death_rate": 0.001, "death_start": 200,
         "q_co2": 0.11, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85,
         "PAA_c": 530000.0, "m_paa": 1.0, "Y_O2_X": 650, "Y_O2_P": 160, "m_O2_X": 17.5},
    60: {"mux": 0.47, "mup": 0.035, "dist_tcin_asym": 15, "m_s": 0.010,
         "q_co2": 0.1, "Y_NX": 20, "Y_NP": 40, "alpha_kla": 85,
         "PAA_c": 530000.0, "m_paa": 1.0},
    80: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 18, "m_s": 0.029,
         "biomass_death_rate": 0.005, "death_start": 0,
         "q_co2": 0.13, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85, "vis_scale": 0.9,
         "PAA_c": 400000.0, "m_paa": 0.3, "Y_O2_X": 800, "Y_O2_P": 120, "m_O2_X": 17.5},
    91: {"mux": 0.47, "mup": 0.055, "dist_tcin_asym": 20, "m_s": 0.029,
         "biomass_death_rate": 0.005, "death_start": 200,
         "q_co2": 0.11, "Y_NX": 12, "Y_NP": 60, "alpha_kla": 130, "vis_scale": 0.9,
         "PAA_c": 530000.0, "m_paa": 0.7, "Y_O2_X": 650, "Y_O2_P": 160, "m_O2_X": 17.5},
    92: {"mux": 0.41, "mup": 0.055, "dist_tcin_asym": 20, "m_s": 0.029,
         "biomass_death_rate": 0.001, "death_start": 100,
         "q_co2": 0.12, "Y_NX": 10, "Y_NP": 80, "alpha_kla": 90, "vis_scale": 0.9,
         "PAA_c": 530000.0, "m_paa": 1.0, "Y_O2_X": 650, "Y_O2_P": 200, "m_O2_X": 17.5},
}


def build_params(cp):
    """Build params dict from combined params, with mu_h_scale passthrough."""
    params = {}
    for k, v in cp.items():
        if k in ("mux", "mup", "alpha_kla", "PAA_c", "m_paa", "Y_O2_X", "Y_O2_P",
                 "m_O2_X", "q_co2", "Y_NX", "Y_NP", "vis_scale", "dist_tcin_asym",
                 "m_s", "m_s_schedule", "biomass_death_rate", "death_start", "mu_h_scale"):
            params[k] = v
    return params


def main():
    print("=" * 80, flush=True)
    print("R129ai: mu_h_scale sweep on golden batches with yield errors", flush=True)
    print("=" * 80, flush=True)

    # Batches to test: those with yield_err > 2% in current golden set
    batches_to_test = [27, 23, 91]

    all_results = {}

    for b in batches_to_test:
        v3 = pd.read_csv(f"data/processed/batches/batch_{b:02d}.csv")
        cp = COMBINED[b]
        base_params = build_params(cp)

        print("\n--- Batch {} (current yield_err) ---".format(b), flush=True)

        # Baseline (no mu_h_scale)
        sim_base, _ = simulate_open_loop(b, base_params)
        ym_base = yield_metrics(sim_base, v3)
        base_err = ym_base["rel_err_total"]
        print("  Baseline (no mu_h_scale): yield_err={:+.4f} ({:+.1f}%)".format(
            base_err, base_err * 100), flush=True)

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

    # Save
    dst = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "runs", "p3", "d9_muh_scale_golden_sweep.json")
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print("\nSaved: %s" % dst, flush=True)


if __name__ == "__main__":
    main()

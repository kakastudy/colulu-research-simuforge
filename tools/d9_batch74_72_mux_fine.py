# -*- coding: utf-8 -*-
"""R129ak2: Fine-tune mux for Batch 74 and 72.

Batch 74: mux=0.60 → yield_err=-0.7%
Batch 72: mux=0.55 → yield_err=-0.1%

The issue: sim pH drops to 3.0 (acidic) while V3 pH stays at 6.5.
Higher mux stabilizes pH through biomass growth dynamics.
Find optimal mux with fine sweep.
"""
import os
import sys
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
    for key in ["m_paa", "m_s_schedule", "biomass_death_rate", "death_start",
                "q_co2", "Y_NX", "Y_NP", "vis_scale", "Y_O2_X", "Y_O2_P",
                "m_O2_X", "mu_h_scale"]:
        if key in cp:
            if key == "biomass_death_rate":
                params["biomass_death_rate"] = cp["biomass_death_rate"]
                params["death_start"] = cp["death_start"]
            else:
                params[key] = cp[key]
    return params


NOMINAL = {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
           "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85}


def main():
    print("=" * 80, flush=True)
    print("R129ak2: Fine-tune mux for Batch 74 and 72", flush=True)
    print("=" * 80, flush=True)

    for b, mux_range in [(74, [0.55, 0.56, 0.57, 0.58, 0.59, 0.60, 0.61, 0.62, 0.63, 0.64, 0.65]),
                          (72, [0.45, 0.46, 0.47, 0.48, 0.49, 0.50, 0.51, 0.52, 0.53, 0.54, 0.55, 0.56, 0.57])]:
        v3 = pd.read_csv(f"data/processed/batches/batch_{b:02d}.csv")
        cp = dict(NOMINAL)

        print("\n--- Batch {} ---".format(b), flush=True)

        best_err = None
        best_mux = 0.35

        for mux in mux_range:
            cp2 = dict(cp)
            cp2["mux"] = mux
            params = build_params(cp2)
            try:
                sim, _ = simulate_open_loop(b, params)
                ym = yield_metrics(sim, v3)
                err = ym["rel_err_total"]
                p_final = float(sim["P"].iloc[-1])
                x_final = float(sim["X"].iloc[-1])
                ph_end = float(sim["pH"].iloc[-1])
                if best_err is None or abs(err) < abs(best_err):
                    best_err = err
                    best_mux = mux
                marker = " ***" if abs(err) < 0.03 else ""
                print("  mux={:.2f}: yield_err={:+.4f} ({:+.1f}%) P_final={:.2f} X_final={:.1f} pH_end={:.2f}{}".format(
                    mux, err, err * 100, p_final, x_final, ph_end, marker), flush=True)
            except Exception as e:
                print("  mux={:.2f}: FAILED - {}".format(mux, str(e)[:50]), flush=True)

        print("\n  Best: mux={:.2f} yield_err={:+.4f} ({:+.1f}%)".format(
            best_mux, best_err, best_err * 100), flush=True)


if __name__ == "__main__":
    main()

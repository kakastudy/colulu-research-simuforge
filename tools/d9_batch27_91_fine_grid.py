# -*- coding: utf-8 -*-
"""R129ai6: Fine-grained grid around best params for Batch 27 and 91.

Batch 27: mup=0.040, mux=0.36 → yield_err=+3.4%
Batch 91: mup=0.040, mux=0.40 → yield_err=+3.5%

Try finer grid to find even better combinations.
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


COMBINED = {
    27: {"mux": 0.36, "mup": 0.040, "dist_tcin_asym": 15, "m_s": 0.029,
         "m_s_schedule": [(140, 0.018)], "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40,
         "alpha_kla": 85, "vis_scale": 0.9,
         "PAA_c": 530000.0, "m_paa": 1.0, "Y_O2_X": 650, "Y_O2_P": 160, "m_O2_X": 15},
    91: {"mux": 0.40, "mup": 0.040, "dist_tcin_asym": 10, "m_s": 0.029,
         "biomass_death_rate": 0.005, "death_start": 200,
         "q_co2": 0.12, "Y_NX": 10, "Y_NP": 60, "alpha_kla": 90},
}


def main():
    print("=" * 80, flush=True)
    print("R129ai6: Fine-grained grid for Batch 27 and 91", flush=True)
    print("=" * 80, flush=True)

    for b in [27, 91]:
        v3 = pd.read_csv(f"data/processed/batches/batch_{b:02d}.csv")
        cp = COMBINED[b]

        print("\n--- Batch {} (current: mux={}, mup={}) ---".format(
            b, cp["mux"], cp["mup"]), flush=True)

        best_err = None
        best_mux = cp["mux"]
        best_mup = cp["mup"]

        for mux in np.arange(cp["mux"] - 0.01, cp["mux"] + 0.02, 0.005):
            for mup in np.arange(cp["mup"] - 0.002, cp["mup"] + 0.003, 0.001):
                mux_v = round(mux, 3)
                mup_v = round(mup, 3)
                cp2 = dict(cp)
                cp2["mux"] = mux_v
                cp2["mup"] = mup_v
                params = build_params(cp2)
                try:
                    sim, _ = simulate_open_loop(b, params)
                    ym = yield_metrics(sim, v3)
                    err = ym["rel_err_total"]
                    if best_err is None or abs(err) < abs(best_err):
                        best_err = err
                        best_mux = mux_v
                        best_mup = mup_v
                    marker = " ***" if abs(err) < 0.02 else ""
                    print("  mux={:.3f} mup={:.3f}: yield_err={:+.4f} ({:+.1f}%){}".format(
                        mux_v, mup_v, err, err * 100, marker), flush=True)
                except Exception as e:
                    print("  mux={:.3f} mup={:.3f}: FAILED".format(mux_v, mup_v), flush=True)

        print("\n  Best: mux={} mup={} yield_err={:+.4f} ({:+.1f}%)".format(
            best_mux, best_mup, best_err, best_err * 100), flush=True)


if __name__ == "__main__":
    main()

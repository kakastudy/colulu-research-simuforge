# -*- coding: utf-8 -*-
"""R129ap: Fine mux sweep for Batch 87 (best +5.3% at mux=0.60)."""
import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))

from simulate import simulate_open_loop, yield_metrics


def build_params(cp):
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
    print("R129ap: Fine mux sweep for Batch 87", flush=True)
    print("=" * 80, flush=True)

    b = 87
    v3 = pd.read_csv(f"data/processed/batches/batch_{b:02d}.csv")
    cp = dict(NOMINAL)

    best_err = None
    for mux in np.arange(0.60, 0.81, 0.02):
        cp2 = dict(cp)
        cp2["mux"] = round(mux, 2)
        params = build_params(cp2)
        try:
            sim, _ = simulate_open_loop(b, params)
            ym = yield_metrics(sim, v3)
            err = ym["rel_err_total"]
            if best_err is None or abs(err) < abs(best_err):
                best_err = err
                best_mux = round(mux, 2)
            print("  mux={:.2f}: yield_err={:+.4f} ({:+.1f}%) P_final={:.2f}{}".format(
                round(mux, 2), err, err * 100, float(sim["P"].iloc[-1]),
                " ***" if abs(err) < 0.05 else ""), flush=True)
        except Exception as e:
            print("  mux={:.2f}: FAILED".format(round(mux, 2)), flush=True)

    print("\nBest: mux={} yield_err={:+.4f} ({:+.1f}%)".format(best_mux, best_err, best_err * 100), flush=True)


if __name__ == "__main__":
    main()

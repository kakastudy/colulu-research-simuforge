# -*- coding: utf-8 -*-
"""R129ai5: Fine-grained mup/mux sweep for Batch 91 to reduce yield error.

Batch 91: yield_err=+4.3%, fault batch, pH_end=3.0
Sim overproduces harvested (+30.1%) but underproduces end-in-vessel (-41.5%)
Temporal distribution error in fault batch.
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


COMBINED_91 = {"mux": 0.39, "mup": 0.041, "dist_tcin_asym": 10, "m_s": 0.029,
               "biomass_death_rate": 0.005, "death_start": 200,
               "q_co2": 0.12, "Y_NX": 10, "Y_NP": 60, "alpha_kla": 90}


def main():
    print("=" * 80, flush=True)
    print("R129ai5: Fine-grained mup/mux sweep for Batch 91", flush=True)
    print("=" * 80, flush=True)

    b = 91
    v3 = pd.read_csv(f"data/processed/batches/batch_{b:02d}.csv")
    cp = COMBINED_91

    # Baseline
    params = build_params(cp)
    sim, _ = simulate_open_loop(b, params)
    ym = yield_metrics(sim, v3)
    base_err = ym["rel_err_total"]
    print("Baseline (mux=0.39, mup=0.041): yield_err={:+.4f} ({:+.1f}%) P_final={:.2f}".format(
        base_err, base_err * 100, float(sim["P"].iloc[-1])), flush=True)

    # Sweep mup
    print("\n--- mup sweep ---", flush=True)
    best_err = base_err
    best_params = {"mux": 0.39, "mup": 0.041}

    for mup in [0.039, 0.040, 0.041, 0.042, 0.043, 0.045]:
        cp2 = dict(cp)
        cp2["mup"] = mup
        params = build_params(cp2)
        try:
            sim, _ = simulate_open_loop(b, params)
            ym = yield_metrics(sim, v3)
            err = ym["rel_err_total"]
            p_final = float(sim["P"].iloc[-1])
            marker = " ***" if abs(err) < 0.05 else ""
            print("  mup={:.3f}: yield_err={:+.4f} ({:+.1f}%) P_final={:.2f}{}".format(
                mup, err, err * 100, p_final, marker), flush=True)
            if abs(err) < abs(best_err):
                best_err = err
                best_params = {"mux": 0.39, "mup": mup}
        except Exception as e:
            print("  mup={:.3f}: FAILED - {}".format(mup, str(e)[:50]), flush=True)

    # Sweep mux
    print("\n--- mux sweep ---", flush=True)
    for mux in [0.37, 0.38, 0.39, 0.40, 0.41, 0.42]:
        cp2 = dict(cp)
        cp2["mux"] = mux
        params = build_params(cp2)
        try:
            sim, _ = simulate_open_loop(b, params)
            ym = yield_metrics(sim, v3)
            err = ym["rel_err_total"]
            p_final = float(sim["P"].iloc[-1])
            marker = " ***" if abs(err) < 0.05 else ""
            print("  mux={:.2f}: yield_err={:+.4f} ({:+.1f}%) P_final={:.2f}{}".format(
                mux, err, err * 100, p_final, marker), flush=True)
            if abs(err) < abs(best_err):
                best_err = err
                best_params = {"mux": mux, "mup": cp["mup"]}
        except Exception as e:
            print("  mux={:.2f}: FAILED - {}".format(mux, str(e)[:50]), flush=True)

    # Combined grid
    print("\n--- combined mup*mux grid ---", flush=True)
    for mup in [0.039, 0.040, 0.041]:
        for mux in [0.38, 0.39, 0.40]:
            cp2 = dict(cp)
            cp2["mup"] = mup
            cp2["mux"] = mux
            params = build_params(cp2)
            try:
                sim, _ = simulate_open_loop(b, params)
                ym = yield_metrics(sim, v3)
                err = ym["rel_err_total"]
                p_final = float(sim["P"].iloc[-1])
                marker = " ***" if abs(err) < 0.03 else ""
                print("  mup={:.3f} mux={:.2f}: yield_err={:+.4f} ({:+.1f}%) P_final={:.2f}{}".format(
                    mup, mux, err, err * 100, p_final, marker), flush=True)
                if abs(err) < abs(best_err):
                    best_err = err
                    best_params = {"mux": mux, "mup": mup}
            except Exception as e:
                print("  mup={:.3f} mux={:.2f}: FAILED".format(mup, mux), flush=True)

    print("\nBest: mux={} mup={} yield_err={:+.4f} ({:+.1f}%)".format(
        best_params["mux"], best_params["mup"], best_err, best_err * 100), flush=True)


if __name__ == "__main__":
    main()

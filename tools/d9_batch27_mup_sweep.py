# -*- coding: utf-8 -*-
"""R129ai4: Fine-grained mup/mux sweep for Batch 27 to reduce yield error.

Batch 27: yield_err=+4.8%, P_final=28.8 vs V3 27.4
The model overproduces penicillin. Need to reduce P production slightly.
Current mup=0.041. Try lower values.
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


COMBINED_27 = {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 15, "m_s": 0.029,
               "m_s_schedule": [(140, 0.018)], "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40,
               "alpha_kla": 85, "vis_scale": 0.9,
               "PAA_c": 530000.0, "m_paa": 1.0, "Y_O2_X": 650, "Y_O2_P": 160, "m_O2_X": 15}


def main():
    print("=" * 80, flush=True)
    print("R129ai4: Fine-grained mup sweep for Batch 27", flush=True)
    print("=" * 80, flush=True)

    b = 27
    v3 = pd.read_csv(f"data/processed/batches/batch_{b:02d}.csv")
    cp = COMBINED_27

    # Baseline
    params = build_params(cp)
    sim, _ = simulate_open_loop(b, params)
    ym = yield_metrics(sim, v3)
    base_err = ym["rel_err_total"]
    print("Baseline (mup=0.041): yield_err={:+.4f} ({:+.1f}%) P_final={:.2f}".format(
        base_err, base_err * 100, float(sim["P"].iloc[-1])), flush=True)

    # Sweep mup finely
    print("\n--- mup sweep ---", flush=True)
    best_err = base_err
    best_mup = 0.041
    results = []

    for mup in [0.039, 0.040, 0.041, 0.042, 0.043]:
        cp2 = dict(cp)
        cp2["mup"] = mup
        params = build_params(cp2)
        try:
            sim, _ = simulate_open_loop(b, params)
            ym = yield_metrics(sim, v3)
            err = ym["rel_err_total"]
            p_final = float(sim["P"].iloc[-1])
            results.append({"mup": mup, "yield_err": err, "p_final": p_final})
            if abs(err) < abs(best_err):
                best_err = err
                best_mup = mup
            marker = " ***" if abs(err) < 0.05 else ""
            print("  mup={:.3f}: yield_err={:+.4f} ({:+.1f}%) P_final={:.2f}{}".format(
                mup, err, err * 100, p_final, marker), flush=True)
        except Exception as e:
            print("  mup={:.3f}: FAILED - {}".format(mup, str(e)[:50]), flush=True)

    print("\nBest: mup={:.3f} yield_err={:+.4f} ({:+.1f}%)".format(
        best_mup, best_err, best_err * 100), flush=True)

    # Now try mux sweep
    print("\n--- mux sweep ---", flush=True)
    for mux in [0.34, 0.35, 0.36, 0.37]:
        cp2 = dict(cp)
        cp2["mux"] = mux
        params = build_params(cp2)
        try:
            sim, _ = simulate_open_loop(b, params)
            ym = yield_metrics(sim, v3)
            err = ym["rel_err_total"]
            p_final = float(sim["P"].iloc[-1])
            x_final = float(sim["X"].iloc[-1])
            marker = " ***" if abs(err) < 0.05 else ""
            print("  mux={:.2f}: yield_err={:+.4f} ({:+.1f}%) P_final={:.2f} X_final={:.1f}{}".format(
                mux, err, err * 100, p_final, x_final, marker), flush=True)
        except Exception as e:
            print("  mux={:.2f}: FAILED - {}".format(mux, str(e)[:50]), flush=True)

    # Try combined mup+mux
    print("\n--- combined mup*mux grid ---", flush=True)
    for mup in [0.039, 0.040, 0.041]:
        for mux in [0.34, 0.35, 0.36]:
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
                    best_mup = mup
                    best_mux = mux
            except Exception as e:
                print("  mup={:.3f} mux={:.2f}: FAILED".format(mup, mux), flush=True)

    # Save
    dst = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "runs", "p3", "d9_batch27_mup_sweep.json")
    with open(dst, "w", encoding="utf-8") as f:
        json.dump({"base_err": base_err, "best_mup": best_mup, "best_err": best_err,
                   "results": results}, f, ensure_ascii=False, indent=2)
    print("\nSaved: %s" % dst, flush=True)


if __name__ == "__main__":
    main()

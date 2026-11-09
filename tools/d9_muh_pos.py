# -*- coding: utf-8 -*-
"""R129ct: Test mu_h_scale > 1.0 for remaining positive yield batches (10, 19, 38, 40, 44, 51, 54, 94, 97)."""
import os
import sys
import json
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


def sweep_batch(b, cp):
    v3 = pd.read_csv(f"data/processed/batches/batch_{b:02d}.csv")
    params = build_params(cp)
    sim, _ = simulate_open_loop(b, params)
    ym = yield_metrics(sim, v3)
    base_err = ym["rel_err_total"]
    print("  Baseline: yield_err={:+.4f} ({:+.1f}%) P_final={:.2f}".format(
        base_err, base_err * 100, float(sim["P"].iloc[-1])), flush=True)

    best_err = base_err
    best_params = dict(cp)

    # Test mu_h_scale > 1.0
    for scale in [1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 2.0, 2.5, 3.0]:
        cp2 = dict(cp)
        cp2["mu_h_scale"] = scale
        params = build_params(cp2)
        try:
            sim, _ = simulate_open_loop(b, params)
            ym = yield_metrics(sim, v3)
            err = ym["rel_err_total"]
            if abs(err) < abs(best_err):
                best_err = err
                best_params = dict(cp2)
            print("  mu_h_scale={:.1f}: yield_err={:+.4f} ({:+.1f}%) P_final={:.2f}{}".format(
                scale, err, err * 100, float(sim["P"].iloc[-1]),
                " ***" if abs(err) < 0.05 else ""), flush=True)
        except Exception as e:
            print("  mu_h_scale={:.1f}: FAILED".format(scale), flush=True)

    # Test mu_h_scale > 1.0 + Y_NP < 40
    if abs(best_err) >= 0.05:
        for scale in [1.2, 1.5, 2.0]:
            for ynp in [25, 30, 35]:
                cp2 = dict(cp)
                cp2["mu_h_scale"] = scale
                cp2["Y_NP"] = ynp
                params = build_params(cp2)
                try:
                    sim, _ = simulate_open_loop(b, params)
                    ym = yield_metrics(sim, v3)
                    err = ym["rel_err_total"]
                    if abs(err) < abs(best_err):
                        best_err = err
                        best_params = dict(cp2)
                    print("  mu_h_scale={:.1f}+Y_NP={:.0f}: yield_err={:+.4f} ({:+.1f}%) P_final={:.2f}{}".format(
                        scale, ynp, err, err * 100, float(sim["P"].iloc[-1]),
                        " ***" if abs(err) < 0.05 else ""), flush=True)
                except Exception as e:
                    print("  mu_h_scale={:.1f}+Y_NP={:.0f}: FAILED".format(scale, ynp), flush=True)

    print("  Best: yield_err={:+.4f} ({:+.1f}%)".format(best_err, best_err * 100), flush=True)
    return {"batch": b, "base_err": base_err, "best_err": best_err, "best_params": best_params}


def main():
    print("=" * 80, flush=True)
    print("R129ct: Test mu_h_scale > 1.0 for remaining positive yield batches", flush=True)
    print("=" * 80, flush=True)

    batches = [10, 19, 38, 40, 44, 51, 54, 94, 97]
    all_results = {}
    for b in batches:
        print("\n--- Batch {} ---".format(b), flush=True)
        cp = dict(NOMINAL)
        result = sweep_batch(b, cp)
        all_results[b] = result

    dst = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "runs", "p3", "d9_muh_pos.json")
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2, default=str)
    print("\nSaved: %s" % dst, flush=True)


if __name__ == "__main__":
    main()

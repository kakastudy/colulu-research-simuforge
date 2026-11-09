# -*- coding: utf-8 -*-
"""R129cza2: Fine sweep mu_h_scale < 0.1 for Batch 32 and mu_h_scale 1.4-1.5 for Batch 94."""
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


def sweep_batch(b, cp, label, scales):
    v3 = pd.read_csv(f"data/processed/batches/batch_{b:02d}.csv")
    params = build_params(cp)
    sim, _ = simulate_open_loop(b, params)
    ym = yield_metrics(sim, v3)
    base_err = ym["rel_err_total"]
    print("  [{}] Baseline: yield_err={:+.4f} ({:+.1f}%) P_final={:.2f}".format(
        label, base_err, base_err * 100, float(sim["P"].iloc[-1])), flush=True)

    best_err = base_err
    best_params = dict(cp)

    for scale in scales:
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
            print("  [{}] mu_h_scale={:.3f}: yield_err={:+.4f} ({:+.1f}%) P_final={:.2f}{}".format(
                label, scale, err, err * 100, float(sim["P"].iloc[-1]),
                " ***" if abs(err) < 0.05 else ""), flush=True)
        except Exception as e:
            print("  [{}] mu_h_scale={:.3f}: FAILED".format(label, scale), flush=True)

    print("  [{}] Best: yield_err={:+.4f} ({:+.1f}%)".format(label, best_err, best_err * 100), flush=True)
    return {"batch": b, "label": label, "base_err": base_err, "best_err": best_err, "best_params": best_params}


def main():
    print("=" * 80, flush=True)
    print("R129cza2: Fine sweep mu_h_scale for Batch 32 and 94", flush=True)
    print("=" * 80, flush=True)

    all_results = {}

    # Batch 32: m_s=0.038+mup=0.08, mu_h_scale < 0.1
    cp32 = dict(NOMINAL)
    cp32["m_s"] = 0.038
    cp32["mup"] = 0.08
    result32 = sweep_batch(32, cp32, "32", [0.0, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.09, 0.10])
    all_results["batch32"] = result32

    # Batch 94: mu_h_scale 1.4-1.5
    cp94 = dict(NOMINAL)
    result94 = sweep_batch(94, cp94, "94", [1.40, 1.41, 1.42, 1.43, 1.44, 1.45, 1.46, 1.47, 1.48, 1.49, 1.50])
    all_results["batch94"] = result94

    dst = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "runs", "p3", "d9_batch32_94_fine.json")
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2, default=str)
    print("\nSaved: %s" % dst, flush=True)


if __name__ == "__main__":
    main()

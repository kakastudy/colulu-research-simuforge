# -*- coding: utf-8 -*-
"""R129cn: Fine sweep PAA_c + mup for Batch 94 (PAA_c=600000+mup=0.07 -> -31.6%, +0.08 -> +27.2%)."""
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

    # Fine sweep PAA_c around 600000
    for paac in [550000, 570000, 580000, 590000, 600000, 610000, 620000, 630000, 650000]:
        cp2 = dict(cp)
        cp2["PAA_c"] = paac
        cp2["mup"] = 0.07
        params = build_params(cp2)
        try:
            sim, _ = simulate_open_loop(b, params)
            ym = yield_metrics(sim, v3)
            err = ym["rel_err_total"]
            if abs(err) < abs(best_err):
                best_err = err
                best_params = dict(cp2)
            print("  PAA_c={:.0f}+mup=0.07: yield_err={:+.4f} ({:+.1f}%) P_final={:.2f}{}".format(
                paac, err, err * 100, float(sim["P"].iloc[-1]),
                " ***" if abs(err) < 0.05 else ""), flush=True)
        except Exception as e:
            print("  PAA_c={:.0f}+mup=0.07: FAILED".format(paac), flush=True)

    # Fine sweep mup around 0.075
    for mup in [0.071, 0.072, 0.073, 0.074, 0.075, 0.076, 0.077, 0.078, 0.079]:
        cp2 = dict(cp)
        cp2["PAA_c"] = 600000
        cp2["mup"] = mup
        params = build_params(cp2)
        try:
            sim, _ = simulate_open_loop(b, params)
            ym = yield_metrics(sim, v3)
            err = ym["rel_err_total"]
            if abs(err) < abs(best_err):
                best_err = err
                best_params = dict(cp2)
            print("  PAA_c=600000+mup={:.3f}: yield_err={:+.4f} ({:+.1f}%) P_final={:.2f}{}".format(
                mup, err, err * 100, float(sim["P"].iloc[-1]),
                " ***" if abs(err) < 0.05 else ""), flush=True)
        except Exception as e:
            print("  PAA_c=600000+mup={:.3f}: FAILED".format(mup), flush=True)

    # Combined PAA_c + mup fine sweep
    if abs(best_err) >= 0.05:
        for paac in [580000, 590000, 600000, 610000, 620000]:
            for mup in [0.072, 0.073, 0.074, 0.075, 0.076, 0.077, 0.078]:
                cp2 = dict(cp)
                cp2["PAA_c"] = paac
                cp2["mup"] = mup
                params = build_params(cp2)
                try:
                    sim, _ = simulate_open_loop(b, params)
                    ym = yield_metrics(sim, v3)
                    err = ym["rel_err_total"]
                    if abs(err) < abs(best_err):
                        best_err = err
                        best_params = dict(cp2)
                    print("  PAA_c={:.0f}+mup={:.3f}: yield_err={:+.4f} ({:+.1f}%) P_final={:.2f}{}".format(
                        paac, mup, err, err * 100, float(sim["P"].iloc[-1]),
                        " ***" if abs(err) < 0.05 else ""), flush=True)
                except Exception as e:
                    print("  PAA_c={:.0f}+mup={:.3f}: FAILED".format(paac, mup), flush=True)

    print("  Best: yield_err={:+.4f} ({:+.1f}%)".format(best_err, best_err * 100), flush=True)
    return {"batch": b, "base_err": base_err, "best_err": best_err, "best_params": best_params}


def main():
    print("=" * 80, flush=True)
    print("R129cn: Fine sweep PAA_c + mup for Batch 94", flush=True)
    print("=" * 80, flush=True)

    cp = dict(NOMINAL)
    result = sweep_batch(94, cp)

    dst = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "runs", "p3", "d9_batch94_fine_sweep.json")
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)
    print("\nSaved: %s" % dst, flush=True)


if __name__ == "__main__":
    main()

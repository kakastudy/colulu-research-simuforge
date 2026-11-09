# -*- coding: utf-8 -*-
"""R129cp: Fine sweep PAA_c + alpha_kla for Batch 37 and 51."""
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


def sweep_batch(b, cp, label):
    v3 = pd.read_csv(f"data/processed/batches/batch_{b:02d}.csv")
    params = build_params(cp)
    sim, _ = simulate_open_loop(b, params)
    ym = yield_metrics(sim, v3)
    base_err = ym["rel_err_total"]
    print("  [{}] Baseline: yield_err={:+.4f} ({:+.1f}%) P_final={:.2f}".format(
        label, base_err, base_err * 100, float(sim["P"].iloc[-1])), flush=True)

    best_err = base_err
    best_params = dict(cp)

    if label == "37":
        # Fine sweep PAA_c around 800000 + mup around 0.07
        for paac in [750000, 770000, 780000, 790000, 800000, 810000, 820000, 830000, 850000]:
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
                print("  [37] PAA_c={:.0f}+mup=0.07: yield_err={:+.4f} ({:+.1f}%) P_final={:.2f}{}".format(
                    paac, err, err * 100, float(sim["P"].iloc[-1]),
                    " ***" if abs(err) < 0.05 else ""), flush=True)
            except Exception as e:
                print("  [37] PAA_c={:.0f}+mup=0.07: FAILED".format(paac), flush=True)

        # Fine sweep mup around 0.07 with PAA_c=800000
        for mup in [0.071, 0.072, 0.073, 0.074, 0.075, 0.076, 0.077, 0.078, 0.079]:
            cp2 = dict(cp)
            cp2["PAA_c"] = 800000
            cp2["mup"] = mup
            params = build_params(cp2)
            try:
                sim, _ = simulate_open_loop(b, params)
                ym = yield_metrics(sim, v3)
                err = ym["rel_err_total"]
                if abs(err) < abs(best_err):
                    best_err = err
                    best_params = dict(cp2)
                print("  [37] PAA_c=800000+mup={:.3f}: yield_err={:+.4f} ({:+.1f}%) P_final={:.2f}{}".format(
                    mup, err, err * 100, float(sim["P"].iloc[-1]),
                    " ***" if abs(err) < 0.05 else ""), flush=True)
            except Exception as e:
                print("  [37] PAA_c=800000+mup={:.3f}: FAILED".format(mup), flush=True)

        # Combined PAA_c + mup fine sweep
        if abs(best_err) >= 0.05:
            for paac in [780000, 790000, 800000, 810000, 820000]:
                for mup in [0.071, 0.072, 0.073, 0.074, 0.075, 0.076, 0.077, 0.078]:
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
                        print("  [37] PAA_c={:.0f}+mup={:.3f}: yield_err={:+.4f} ({:+.1f}%) P_final={:.2f}{}".format(
                            paac, mup, err, err * 100, float(sim["P"].iloc[-1]),
                            " ***" if abs(err) < 0.05 else ""), flush=True)
                    except Exception as e:
                        print("  [37] PAA_c={:.0f}+mup={:.3f}: FAILED".format(paac, mup), flush=True)
    else:
        # Fine sweep alpha_kla around 120 + mup around 0.08 for Batch 51
        for akl in [100, 110, 115, 120, 125, 130, 140, 150]:
            cp2 = dict(cp)
            cp2["alpha_kla"] = akl
            cp2["mup"] = 0.08
            params = build_params(cp2)
            try:
                sim, _ = simulate_open_loop(b, params)
                ym = yield_metrics(sim, v3)
                err = ym["rel_err_total"]
                if abs(err) < abs(best_err):
                    best_err = err
                    best_params = dict(cp2)
                print("  [51] alpha_kla={:.0f}+mup=0.08: yield_err={:+.4f} ({:+.1f}%) P_final={:.2f}{}".format(
                    akl, err, err * 100, float(sim["P"].iloc[-1]),
                    " ***" if abs(err) < 0.05 else ""), flush=True)
            except Exception as e:
                print("  [51] alpha_kla={:.0f}+mup=0.08: FAILED".format(akl), flush=True)

        # Fine sweep mup around 0.08 with alpha_kla=120
        for mup in [0.081, 0.082, 0.083, 0.084, 0.085, 0.086, 0.087, 0.088, 0.089, 0.090]:
            cp2 = dict(cp)
            cp2["alpha_kla"] = 120
            cp2["mup"] = mup
            params = build_params(cp2)
            try:
                sim, _ = simulate_open_loop(b, params)
                ym = yield_metrics(sim, v3)
                err = ym["rel_err_total"]
                if abs(err) < abs(best_err):
                    best_err = err
                    best_params = dict(cp2)
                print("  [51] alpha_kla=120+mup={:.3f}: yield_err={:+.4f} ({:+.1f}%) P_final={:.2f}{}".format(
                    mup, err, err * 100, float(sim["P"].iloc[-1]),
                    " ***" if abs(err) < 0.05 else ""), flush=True)
            except Exception as e:
                print("  [51] alpha_kla=120+mup={:.3f}: FAILED".format(mup), flush=True)

        # Combined alpha_kla + mup fine sweep
        if abs(best_err) >= 0.05:
            for akl in [100, 110, 120, 130, 140]:
                for mup in [0.082, 0.083, 0.084, 0.085, 0.086, 0.087, 0.088, 0.089]:
                    cp2 = dict(cp)
                    cp2["alpha_kla"] = akl
                    cp2["mup"] = mup
                    params = build_params(cp2)
                    try:
                        sim, _ = simulate_open_loop(b, params)
                        ym = yield_metrics(sim, v3)
                        err = ym["rel_err_total"]
                        if abs(err) < abs(best_err):
                            best_err = err
                            best_params = dict(cp2)
                        print("  [51] alpha_kla={:.0f}+mup={:.3f}: yield_err={:+.4f} ({:+.1f}%) P_final={:.2f}{}".format(
                            akl, mup, err, err * 100, float(sim["P"].iloc[-1]),
                            " ***" if abs(err) < 0.05 else ""), flush=True)
                    except Exception as e:
                        print("  [51] alpha_kla={:.0f}+mup={:.3f}: FAILED".format(akl, mup), flush=True)

    print("  [{}] Best: yield_err={:+.4f} ({:+.1f}%)".format(label, best_err, best_err * 100), flush=True)
    return {"batch": b, "base_err": base_err, "best_err": best_err, "best_params": best_params}


def main():
    print("=" * 80, flush=True)
    print("R129cp: Fine sweep PAA_c/alpha_kla for Batch 37 and 51", flush=True)
    print("=" * 80, flush=True)

    results = {}
    print("\n--- Batch 37 ---", flush=True)
    results[37] = sweep_batch(37, dict(NOMINAL), "37")

    print("\n--- Batch 51 ---", flush=True)
    results[51] = sweep_batch(51, dict(NOMINAL), "51")

    dst = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "runs", "p3", "d9_batch37_51_fine_sweep.json")
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)
    print("\nSaved: %s" % dst, flush=True)


if __name__ == "__main__":
    main()

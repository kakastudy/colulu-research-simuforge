# -*- coding: utf-8 -*-
"""R129cr: Fine sweep m_s for Batch 45 (m_s=0.038 -> +12.1%, sharp transition from -96.1% at m_s=0.036)."""
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

    # Fine sweep m_s around 0.037-0.039
    for ms in [0.0361, 0.0362, 0.0363, 0.0364, 0.0365, 0.0366, 0.0367, 0.0368, 0.0369,
               0.0370, 0.0371, 0.0372, 0.0373, 0.0374, 0.0375, 0.0376, 0.0377, 0.0378, 0.0379,
               0.0380, 0.0381, 0.0382, 0.0383, 0.0384, 0.0385, 0.0386, 0.0387, 0.0388, 0.0389,
               0.0390, 0.0391, 0.0392, 0.0393, 0.0394, 0.0395, 0.0396, 0.0397, 0.0398, 0.0399]:
        cp2 = dict(cp)
        cp2["m_s"] = ms
        params = build_params(cp2)
        try:
            sim, _ = simulate_open_loop(b, params)
            ym = yield_metrics(sim, v3)
            err = ym["rel_err_total"]
            if abs(err) < abs(best_err):
                best_err = err
                best_params = dict(cp2)
            print("  m_s={:.4f}: yield_err={:+.4f} ({:+.1f}%) P_final={:.2f}{}".format(
                ms, err, err * 100, float(sim["P"].iloc[-1]),
                " ***" if abs(err) < 0.05 else ""), flush=True)
        except Exception as e:
            print("  m_s={:.4f}: FAILED".format(ms), flush=True)

    # Combined m_s + mup
    if abs(best_err) >= 0.05:
        for ms in [0.037, 0.0375, 0.038, 0.0385, 0.039]:
            for mup in [0.041, 0.045, 0.050, 0.055, 0.060, 0.065, 0.070]:
                cp2 = dict(cp)
                cp2["m_s"] = ms
                cp2["mup"] = mup
                params = build_params(cp2)
                try:
                    sim, _ = simulate_open_loop(b, params)
                    ym = yield_metrics(sim, v3)
                    err = ym["rel_err_total"]
                    if abs(err) < abs(best_err):
                        best_err = err
                        best_params = dict(cp2)
                    print("  m_s={:.4f}+mup={:.3f}: yield_err={:+.4f} ({:+.1f}%) P_final={:.2f}{}".format(
                        ms, mup, err, err * 100, float(sim["P"].iloc[-1]),
                        " ***" if abs(err) < 0.05 else ""), flush=True)
                except Exception as e:
                    print("  m_s={:.4f}+mup={:.3f}: FAILED".format(ms, mup), flush=True)

    print("  Best: yield_err={:+.4f} ({:+.1f}%)".format(best_err, best_err * 100), flush=True)
    return {"batch": b, "base_err": base_err, "best_err": best_err, "best_params": best_params}


def main():
    print("=" * 80, flush=True)
    print("R129cr: Fine sweep m_s for Batch 45", flush=True)
    print("=" * 80, flush=True)

    cp = dict(NOMINAL)
    result = sweep_batch(45, cp)

    dst = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "runs", "p3", "d9_batch45_fine_sweep.json")
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)
    print("\nSaved: %s" % dst, flush=True)


if __name__ == "__main__":
    main()

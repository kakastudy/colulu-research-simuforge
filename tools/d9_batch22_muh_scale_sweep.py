# -*- coding: utf-8 -*-
"""R129ah: Sweep mu_h_scale for Batch 22.

mu_h_scale multiplies the k4 value (physics-based mu_h from pH/T).
Increasing mu_h_scale increases P degradation, reducing P concentration and yield.

mu_h only appears in: P ODE, pH ODE, heat (Qrxn_P), OUR.
Does NOT appear in S ODE (uses only production part of r_p).
So mu_h_scale is semi-dormant: affects P, pH, T, OUR but NOT S, biomass, CO2, NH3, PAA, vis.
"""
import os
import sys
import json
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))

from simulate import simulate_open_loop, yield_metrics


def build_params(**overrides):
    params = {"mux": 0.35, "mup": 0.065, "alpha_kla": 85.0, "PAA_c": 530000.0,
              "N_conc_paa": 150000.0, "c_oil": 1000.0, "dist_flag": 1,
              "dist_tcin_asym": 20, "m_s": 0.029, "m_s_schedule": [(110, 0.010)],
              "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40}
    params.update(overrides)
    return params


def main():
    b = 22
    v3 = pd.read_csv(f"data/processed/batches/batch_{b:02d}.csv")

    print("=" * 80, flush=True)
    print("R129ah: Batch 22 mu_h_scale sweep", flush=True)
    print("=" * 80, flush=True)

    results = []
    best_err = None
    best_scale = None

    for scale in [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0, 6.0, 8.0, 10.0, 15.0, 20.0, 30.0]:
        params = build_params(mu_h_scale=scale)
        try:
            sim, _ = simulate_open_loop(b, params)
            ym = yield_metrics(sim, v3)
            err = ym["rel_err_total"]
            p_final = float(sim["P"].iloc[-1])
            x_final = float(sim["X"].iloc[-1])
            results.append({"mu_h_scale": scale, "yield_err": err, "p_final": p_final, "x_final": x_final})
            if best_err is None or abs(err) < abs(best_err):
                best_err = err
                best_scale = scale
            marker = " ***" if abs(err) < 0.05 else ""
            print("  mu_h_scale={:.1f}: yield_err={:+.4f} ({:+.1f}%) P_final={:.1f} X_final={:.1f}{}".format(
                scale, err, err * 100, p_final, x_final, marker), flush=True)
        except Exception as e:
            print("  mu_h_scale={:.1f}: FAILED - {}".format(scale, str(e)[:50]), flush=True)

    print("\n--- Best result ---", flush=True)
    print("  mu_h_scale={}: yield_err={:+.4f} ({:+.1f}%)".format(
        best_scale, best_err, best_err * 100), flush=True)

    # Check channel impact
    print("\n--- Channel impact check (scale=1.0 vs scale=best) ---", flush=True)
    params_base = build_params(mu_h_scale=1.0)
    params_best = build_params(mu_h_scale=best_scale)
    sim_base, _ = simulate_open_loop(b, params_base)
    sim_best, _ = simulate_open_loop(b, params_best)

    channels_to_check = ["S", "X", "DO2", "P", "V", "pH", "T", "CO2outgas", "O2", "OUR", "CER", "PAA", "NH3", "vis"]
    for ch in channels_to_check:
        if ch in sim_base.columns and ch in sim_best.columns:
            v_base = sim_base[ch].to_numpy(float)
            v_best = sim_best[ch].to_numpy(float)
            n = min(len(v_base), len(v_best))
            diff = v_best[:n] - v_base[:n]
            max_diff = np.max(np.abs(diff)) if n > 0 else 0
            rel_diff = max_diff / (np.max(np.abs(v_base)) + 1e-12)
            print("  {}: max_diff={:.4f} rel={:.2%}".format(ch, max_diff, rel_diff), flush=True)

    # Save results
    dst = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "runs", "p3", "d9_batch22_muh_scale_sweep.json")
    with open(dst, "w", encoding="utf-8") as f:
        json.dump({"best_scale": best_scale, "best_err": best_err, "results": results}, f, ensure_ascii=False, indent=2)
    print("\nSaved: %s" % dst, flush=True)


if __name__ == "__main__":
    main()

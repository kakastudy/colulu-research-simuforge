# -*- coding: utf-8 -*-
"""R129ah: Sweep biomass_death_rate and death_start for Batch 22.

V3 biomass peaks at ~23.5 around t=156h then declines.
Sim biomass keeps growing to ~34. Adding death rate should fix this.
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
    print("R129ah: Batch 22 biomass death rate sweep", flush=True)
    print("=" * 80, flush=True)

    best_err = None
    best_params = None
    results = []

    # Sweep death_start and death_rate
    for ds in [100, 120, 140, 150, 160, 170, 180, 200]:
        for dr in [0.001, 0.002, 0.003, 0.005, 0.007, 0.010, 0.015]:
            params = build_params(biomass_death_rate=dr, death_start=ds)
            try:
                sim, _ = simulate_open_loop(b, params)
                ym = yield_metrics(sim, v3)
                err = ym["rel_err_total"]
                results.append({"death_start": ds, "death_rate": dr, "yield_err": err})
                if best_err is None or abs(err) < abs(best_err):
                    best_err = err
                    best_params = {"death_start": ds, "death_rate": dr}
                # Print promising ones
                if abs(err) < 0.05:
                    print("  *** death_start={} death_rate={}: yield_err={:+.4f} ({:+.1f}%) ***".format(
                        ds, dr, err, err * 100), flush=True)
            except Exception as e:
                pass

    print("\n--- Best result ---", flush=True)
    print("  death_start={} death_rate={}: yield_err={:+.4f} ({:+.1f}%)".format(
        best_params["death_start"], best_params["death_rate"], best_err, best_err * 100), flush=True)

    # Print top 10
    print("\n--- Top 10 results ---", flush=True)
    sorted_results = sorted(results, key=lambda x: abs(x["yield_err"]))
    for i, r in enumerate(sorted_results[:10]):
        print("  {}. death_start={} death_rate={}: yield_err={:+.4f} ({:+.1f}%)".format(
            i+1, r["death_start"], r["death_rate"], r["yield_err"], r["yield_err"] * 100), flush=True)

    # Also check: what if we use death_start=0 (always active)?
    print("\n--- death_start=0 (always active) ---", flush=True)
    for dr in [0.001, 0.002, 0.003, 0.005, 0.007, 0.010]:
        params = build_params(biomass_death_rate=dr, death_start=0)
        sim, _ = simulate_open_loop(b, params)
        ym = yield_metrics(sim, v3)
        print("  death_rate={}: yield_err={:+.4f} ({:+.1f}%)".format(
            dr, ym["rel_err_total"], ym["rel_err_total"] * 100), flush=True)

    # Save results
    dst = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "runs", "p3", "d9_batch22_death_sweep.json")
    with open(dst, "w", encoding="utf-8") as f:
        json.dump({"best": best_params, "best_err": best_err, "results": sorted_results[:50]}, f, ensure_ascii=False, indent=2)
    print("\nSaved: %s" % dst, flush=True)


if __name__ == "__main__":
    main()

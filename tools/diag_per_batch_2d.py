# -*- coding: utf-8 -*-
"""Per-batch 2D calibration: scan mux x mup for each golden batch.

Finds the best (mux, mup) combination that minimizes |yield_err| while
preventing crash (CO2d < 7.57).
"""
import sys, os, json, time
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from simulate import simulate_open_loop, yield_metrics

GOLDEN_NORMAL = [8, 11, 16, 22, 23, 27, 36, 55, 60, 80]
FAULT = [91, 92]

MUX_GRID = [0.35, 0.41, 0.47]
MUP_GRID = [0.041, 0.055, 0.070]

results = []
for b in GOLDEN_NORMAL + FAULT:
    print(f"\n=== Batch {b} ===", flush=True)
    v3 = pd.read_csv(f"data/processed/batches/batch_{b:02d}.csv")

    best_err = 1e9
    best_params = {}
    best_no_crash = None

    for mux in MUX_GRID:
        for mup in MUP_GRID:
            params = {"mux": mux, "mup": mup, "alpha_kla": 85.0,
                      "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0}
            sim, _ = simulate_open_loop(b, params)
            ym = yield_metrics(sim, v3)
            err = ym["rel_err_total"]
            co2d_max = sim["CO2d"].max()
            crashed = co2d_max > 7.57

            if abs(err) < best_err:
                best_err = abs(err)
                best_params = {"mux": mux, "mup": mup, "err": err,
                               "co2d_max": co2d_max, "crashed": crashed}

            if not crashed and (best_no_crash is None or abs(err) < abs(best_no_crash["err"])):
                best_no_crash = {"mux": mux, "mup": mup, "err": err,
                                  "co2d_max": co2d_max}

            print(f"  mux={mux:.2f} mup={mup:.3f}: err={err:+.1%} CO2d={co2d_max:.2f} "
                  f"{'CRASH' if crashed else 'ok'}", flush=True)

    within5 = best_params.get("err", 1.0) if abs(best_params.get("err", 1.0)) <= 0.05 else 1.0
    no_crash_ok = best_no_crash is not None and abs(best_no_crash["err"]) <= 0.05

    print(f"  Best: mux={best_params['mux']:.2f} mup={best_params['mup']:.3f} "
          f"err={best_params['err']:+.1%} CO2d={best_params['co2d_max']:.2f} "
          f"{'CRASH' if best_params['crashed'] else 'ok'}", flush=True)
    if best_no_crash:
        print(f"  Best no-crash: mux={best_no_crash['mux']:.2f} mup={best_no_crash['mup']:.3f} "
              f"err={best_no_crash['err']:+.1%} CO2d={best_no_crash['co2d_max']:.2f}", flush=True)

    results.append({
        "batch": b,
        "best_mux": best_params["mux"], "best_mup": best_params["mup"],
        "best_err": best_params["err"], "best_co2d": best_params["co2d_max"],
        "best_crashed": best_params["crashed"],
        "best_no_crash_mux": best_no_crash["mux"] if best_no_crash else None,
        "best_no_crash_mup": best_no_crash["mup"] if best_no_crash else None,
        "best_no_crash_err": best_no_crash["err"] if best_no_crash else None,
        "no_crash_within5": no_crash_ok,
    })

# Summary
print(f"\n{'='*60}")
print(f"=== Per-Batch 2D Calibration Summary ===")
nc = sum(1 for r in results if r["best_no_crash_mux"] is not None)
nc5 = sum(1 for r in results if r["no_crash_within5"])
print(f"No crash: {nc}/{len(results)}")
print(f"No crash + within 5%: {nc5}/{len(results)}")

errs = [r["best_err"] for r in results]
print(f"RMSE of best yields: {np.sqrt(np.mean(np.square(errs))):.2%}")

# Save
with open("runs/per_batch_calib.json", "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)
print(f"Saved: runs/per_batch_calib.json")

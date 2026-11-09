# -*- coding: utf-8 -*-
"""Per-batch 3D calibration: scan mux x mup x distTcin_asym.

For each golden batch, find the combination that minimizes |yield_err|
while keeping CO2d < 7.57 (no crash). Saves calibrated params to JSON.
"""
import sys, os, json
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from simulate import simulate_open_loop, yield_metrics

GOLDEN_NORMAL = [8, 11, 16, 22, 23, 27, 36, 55, 60, 80]
FAULT = [91, 92]

MUX_GRID = [0.35, 0.41, 0.47]
MUP_GRID = [0.041, 0.055, 0.070]
TCIN_GRID = [0, 5, 10]  # distTcin_asym: +5/+10 raises Tcin → lower CO2d

all_results = []

for b in GOLDEN_NORMAL + FAULT:
    print(f"\n=== Batch {b} ===", flush=True)
    v3 = pd.read_csv(f"data/processed/batches/batch_{b:02d}.csv")

    best_no_crash = None  # (err, params, co2d)
    best_any = None

    for mux in MUX_GRID:
        for mup in MUP_GRID:
            for dtcin in TCIN_GRID:
                params = {"mux": mux, "mup": mup, "alpha_kla": 85.0,
                          "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0,
                          "dist_flag": 1, "dist_tcin_asym": dtcin}
                sim, _ = simulate_open_loop(b, params)
                ym = yield_metrics(sim, v3)
                err = ym["rel_err_total"]
                co2d_max = sim["CO2d"].max()
                crashed = co2d_max > 7.57

                tag = f"mux={mux:.2f} mup={mup:.3f} dTcin={dtcin:+d}"
                if crashed:
                    print(f"  {tag}: err={err:+.1%} CO2d={co2d_max:.2f} CRASH", flush=True)
                else:
                    print(f"  {tag}: err={err:+.1%} CO2d={co2d_max:.2f} ok", flush=True)

                if best_any is None or abs(err) < abs(best_any.get("err", 1e9)):
                    best_any = {"err": err, "mux": mux, "mup": mup, "dtcin": dtcin,
                                "co2d": co2d_max, "crashed": crashed}

                if not crashed:
                    if best_no_crash is None or abs(err) < abs(best_no_crash["err"]):
                        best_no_crash = {"err": err, "mux": mux, "mup": mup, "dtcin": dtcin,
                                         "co2d": co2d_max}

    print(f"  Best no-crash: {best_no_crash}", flush=True)
    print(f"  Best any: {best_any}", flush=True)

    all_results.append({
        "batch": b,
        "best_no_crash": best_no_crash,
        "best_any": best_any,
    })

# Save
with open("runs/per_batch_3d_calib.json", "w", encoding="utf-8") as f:
    json.dump(all_results, f, indent=2, ensure_ascii=False)
print(f"\nSaved: runs/per_batch_3d_calib.json")

# Summary
nc = sum(1 for r in all_results if r["best_no_crash"])
nc5 = sum(1 for r in all_results if r["best_no_crash"] and abs(r["best_no_crash"]["err"]) <= 0.05)
print(f"\nNo crash: {nc}/{len(all_results)}")
print(f"No crash + within 5%: {nc5}/{len(all_results)}")

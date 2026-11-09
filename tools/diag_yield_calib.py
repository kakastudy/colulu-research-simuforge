# -*- coding: utf-8 -*-
"""Fast per-batch yield calibration: scan mux to find yield within ±5%.

For each batch, scan mux in [0.24, 0.48] and find the value minimizing |yield_err|.
Report which batches can achieve ±5% yield with a single mux adjustment.
"""
import sys, os, json, time
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from simulate import simulate_open_loop, yield_metrics

GOLDEN_NORMAL = [8, 11, 16, 22, 23, 27, 36, 55, 60, 80]

MUX_GRID = [0.24, 0.28, 0.32, 0.36, 0.40, 0.44, 0.48]

results = []
for b in GOLDEN_NORMAL:
    print(f"\n=== Batch {b} ===", flush=True)
    v3 = pd.read_csv(f"data/processed/batches/batch_{b:02d}.csv")

    best_err = 1e9
    best_mux = 0.41
    best_info = {}

    for mux in MUX_GRID:
        params = {"mux": mux, "mup": 0.041, "alpha_kla": 85.0,
                  "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0}
        sim, _ = simulate_open_loop(b, params)
        ym = yield_metrics(sim, v3)
        err = ym["rel_err_total"]
        co2d_max = sim["CO2d"].max()
        crashed = co2d_max > 7.57
        print(f"  mux={mux:.2f}: yield={ym['total_sim_g']:>12,.0f} "
              f"err={err:+.1%} CO2d={co2d_max:.2f} {'CRASH' if crashed else 'ok'}", flush=True)
        if abs(err) < best_err:
            best_err = abs(err)
            best_mux = mux
            best_info = {"yield_sim": ym["total_sim_g"], "yield_v3": ym["total_v3_g"],
                        "err": err, "co2d_max": co2d_max, "crashed": crashed}

    within5 = abs(best_info.get("err", 1.0)) <= 0.05
    ok_mark = "OK +5%" if within5 else "FAIL >5%"
    print(f"  Best mux={best_mux:.2f}: err={best_info.get('err',0):+.1%} "
          f"CO2d={best_info.get('co2d_max',0):.2f} "
          f"{'CRASH' if best_info.get('crashed') else 'ok'} "
          f"{ok_mark}", flush=True)
    results.append({
        "batch": b, "best_mux": best_mux, "best_err": best_info.get("err", 1.0),
        "within5": within5, "co2d_max": best_info.get("co2d_max", 0),
        "crashed": best_info.get("crashed", False),
    })

# Summary
print(f"\n{'='*60}")
print(f"=== Yield Calibration Summary ===")
n_within = sum(1 for r in results if r["within5"])
n_nocrash = sum(1 for r in results if not r["crashed"])
print(f"Within ±5% yield: {n_within}/{len(results)}")
print(f"No crash: {n_nocrash}/{len(results)}")
print(f"Both: {sum(1 for r in results if r['within5'] and not r['crashed'])}/{len(results)}")

errs = [r["best_err"] for r in results]
print(f"RMSE of best yields: {np.sqrt(np.mean(np.square(errs))):.2%}")

with open("runs/yield_calibration.json", "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)
print(f"\nSaved: runs/yield_calibration.json")

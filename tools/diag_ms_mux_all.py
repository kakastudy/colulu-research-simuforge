# -*- coding: utf-8 -*-
"""Per-batch 2D scan: m_s x mux with dTcin=+10 (fixed).

For each golden batch, find the best (m_s, mux) combination that:
1. Does not crash (CO2d < 7.57)
2. Minimizes |yield_err|

Saves results to runs/ms_mux_calib.json.
"""
import sys, os, json
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from simulate import simulate_open_loop, yield_metrics

GOLDEN = [8, 11, 16, 22, 23, 27, 36, 55, 60, 80, 91, 92]
M_S_GRID = [0.029, 0.025, 0.020, 0.015, 0.012, 0.010]
MUX_GRID = [0.35, 0.41, 0.47]

results = []

for b in GOLDEN:
    d = pd.read_csv(f"data/processed/batches/batch_{b:02d}.csv")
    print(f"\n=== Batch {b} ===", flush=True)
    best_no_crash = None
    best_any = None

    for m_s in M_S_GRID:
        for mux in MUX_GRID:
            params = {"mux": mux, "mup": 0.041, "alpha_kla": 85.0,
                      "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0,
                      "dist_flag": 1, "dist_tcin_asym": 10, "m_s": m_s}
            sim, _ = simulate_open_loop(b, params)
            ym = yield_metrics(sim, d)
            err = ym["rel_err_total"]
            co2d_max = sim["CO2d"].max()
            crashed = co2d_max > 7.57

            tag = f"m_s={m_s:.4f} mux={mux:.2f}"
            status = "CRASH" if crashed else "ok"
            print(f"  {tag}: yield={err:+.1%} CO2d={co2d_max:.2f} {status}", flush=True)

            if best_any is None or abs(err) < abs(best_any["err"]):
                best_any = {"err": err, "m_s": m_s, "mux": mux, "co2d": co2d_max, "crashed": bool(crashed)}

            if not crashed:
                if best_no_crash is None or abs(err) < abs(best_no_crash["err"]):
                    best_no_crash = {"err": err, "m_s": m_s, "mux": mux, "co2d": co2d_max}

    print(f"  Best no-crash: {best_no_crash}", flush=True)
    results.append({
        "batch": b,
        "best_no_crash": best_no_crash,
        "best_any": best_any,
    })

# Save
with open("runs/ms_mux_calib.json", "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2, ensure_ascii=False, default=str)

# Summary
nc = sum(1 for r in results if r["best_no_crash"])
nc5 = sum(1 for r in results if r["best_no_crash"] and abs(r["best_no_crash"]["err"]) <= 0.05)
print(f"\n=== Summary ===")
print(f"No crash: {nc}/{len(results)}")
print(f"No crash + within 5%: {nc5}/{len(results)}")

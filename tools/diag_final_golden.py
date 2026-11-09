# -*- coding: utf-8 -*-
"""Final golden set validation with calibrated params (dTcin=-12, mup=0.060)."""
import sys, os
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from simulate import simulate_open_loop, yield_metrics

GOLDEN_NORMAL = [8, 11, 16, 22, 23, 27, 36, 55, 60, 80]

params = {
    "mux": 0.41, "alpha_kla": 85.0, "mup": 0.060,
    "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0,
    "dist_flag": 1, "dist_tcin_asym": -12,
}

print("=== Golden Set Validation (calibrated: mup=0.060, dTcin=-12) ===")
results = []
for b in GOLDEN_NORMAL:
    v3 = pd.read_csv(f"data/processed/batches/batch_{b:02d}.csv")
    sim, _ = simulate_open_loop(b, params)
    ym = yield_metrics(sim, v3)
    co2d_max = sim["CO2d"].max()
    crashed = co2d_max > 7.57
    status = "CRASH" if crashed else "ok"
    print(f"Batch {b:3d}: yield={ym['total_sim_g']:>12,.0f} "
          f"(V3={ym['total_v3_g']:>12,.0f}) err={ym['rel_err_total']:+.1%} "
          f"CO2d={co2d_max:.2f} {status}")
    results.append({"batch": b, "yield_sim": ym["total_sim_g"], "yield_v3": ym["total_v3_g"],
                    "yield_rel_err": ym["rel_err_total"], "co2d_max": co2d_max, "crashed": crashed})

ok = [r for r in results if not r["crashed"]]
crashed = [r for r in results if r["crashed"]]
print(f"\n=== Summary ===")
print(f"No crash: {len(ok)}/{len(results)}")
print(f"Crash: {len(crashed)}/{len(results)}")
if ok:
    errs = [r["yield_rel_err"] for r in ok]
    print(f"Yield RMSE (no-crash): {np.sqrt(np.mean(np.square(errs))):.2%}")

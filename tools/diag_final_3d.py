# -*- coding: utf-8 -*-
"""Final validation with improved 3D calibrated params (m_s x mup x dTcin)."""
import sys, os, json
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from simulate import simulate_open_loop, yield_metrics

COMBINED = {
    8:  {"mux": 0.47, "mup": 0.041, "dist_tcin_asym": 10, "m_s": 0.029},
    11: {"mux": 0.41, "mup": 0.041, "dist_tcin_asym": 10, "m_s": 0.020},
    16: {"mux": 0.41, "mup": 0.041, "dist_tcin_asym": 10, "m_s": 0.029},
    22: {"mux": 0.41, "mup": 0.070, "dist_tcin_asym": 10, "m_s": 0.029},
    23: {"mux": 0.35, "mup": 0.070, "dist_tcin_asym": 10, "m_s": 0.029},
    27: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 10, "m_s": 0.020},
    36: {"mux": 0.41, "mup": 0.041, "dist_tcin_asym": 10, "m_s": 0.015},
    55: {"mux": 0.47, "mup": 0.055, "dist_tcin_asym": 10, "m_s": 0.029},
    60: {"mux": 0.47, "mup": 0.030, "dist_tcin_asym": 15, "m_s": 0.020},
    80: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 10, "m_s": 0.025},
    91: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 0, "m_s": 0.029},
    92: {"mux": 0.47, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.020},
}

GOLDEN_NORMAL = [8, 11, 16, 22, 23, 27, 36, 55, 60, 80]
FAULT = [91, 92]

print("=== Final Golden Set Validation (3D m_s x mup x dTcin calibrated) ===")
print(f"{'Batch':>6s} {'Type':>6s} {'yield_sim':>12s} {'yield_v3':>12s} {'err':>8s} {'CO2d':>6s} {'status':>6s}")

all_errs = []
results = []
for b in GOLDEN_NORMAL + FAULT:
    v3 = pd.read_csv(f"data/processed/batches/batch_{b:02d}.csv")
    cp = COMBINED[b]
    params = {"mux": cp["mux"], "mup": cp["mup"], "alpha_kla": 85.0,
              "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0,
              "dist_flag": 1, "dist_tcin_asym": cp["dist_tcin_asym"], "m_s": cp["m_s"]}
    sim, _ = simulate_open_loop(b, params)
    ym = yield_metrics(sim, v3)
    co2d_max = sim["CO2d"].max()
    crashed = co2d_max > 7.57
    status = "CRASH" if crashed else "ok"
    batch_type = "normal" if b in GOLDEN_NORMAL else "fault"
    print(f"{b:>6d} {batch_type:>6s} {ym['total_sim_g']:>12,.0f} {ym['total_v3_g']:>12,.0f} "
          f"{ym['rel_err_total']:>+8.1%} {co2d_max:>6.2f} {status:>6s}")
    all_errs.append(ym["rel_err_total"])
    results.append({
        "batch": b, "type": batch_type, "yield_sim": ym["total_sim_g"],
        "yield_v3": ym["total_v3_g"], "yield_err": ym["rel_err_total"],
        "co2d_max": co2d_max, "crashed": bool(crashed),
        "params": cp,
    })

with open("runs/final_3d_validation.json", "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2, ensure_ascii=False, default=str)

rmse = np.sqrt(np.mean(np.square(all_errs)))
n_crash = sum(1 for r in results if r["crashed"])
n_within5 = sum(1 for r in results if not r["crashed"] and abs(r["yield_err"]) <= 0.05)
print(f"\n=== Summary ===")
print(f"Crash: {n_crash}/{len(results)}")
print(f"No crash + within ±5%: {n_within5}/{len(results)}")
print(f"RMSE of yields: {rmse:.2%}")
print(f"\nPrevious (combined 3D+m_s): RMSE=32.57%")
print(f"Previous (3D calib): RMSE=37.40%")

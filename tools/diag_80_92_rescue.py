# -*- coding: utf-8 -*-
"""批 80/92：P_offline 锚定下生长参数联合扫描（mux × mup，m_s=0.029 固定），
试图救 stage-1 生长参数失配批（PROBLEM.md §14.3 残余）。
"""
import sys, os, json
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from simulate import simulate_open_loop, yield_metrics
from diag_b_stage2 import p_offline_rmse

BATCHES = {
    80: {"m_s": 0.029, "dist_tcin_asym": 20},
    92: {"m_s": 0.029, "dist_tcin_asym": 18},
}
MUX_GRID = [0.39, 0.41, 0.43, 0.47]
MUP_GRID = [0.041, 0.050, 0.060, 0.070]

results = []
for b, base in BATCHES.items():
    d = pd.read_csv(f"data/processed/batches/batch_{b:02d}.csv")
    rows = []
    for mux in MUX_GRID:
        for mup in MUP_GRID:
            params = dict(base, mux=mux, mup=mup, alpha_kla=85.0,
                          PAA_c=530000.0, N_conc_paa=150000.0, c_oil=1000.0, dist_flag=1)
            sim, v3 = simulate_open_loop(b, params)
            pr, n = p_offline_rmse(sim, v3)
            ym = yield_metrics(sim, v3)
            rows.append({"mux": mux, "mup": mup, "p_rmse": round(pr, 2),
                         "yield_err": round(ym["rel_err_total"], 3),
                         "co2d": round(sim["CO2d"].max(), 2)})
    rows_sorted = sorted(rows, key=lambda r: r["p_rmse"])
    best = rows_sorted[0]
    results.append({"batch": b, "best": best, "all": rows})
    good = [r for r in rows if abs(r["yield_err"]) <= 0.10 and r["co2d"] <= 7.57]
    bmsg = f"batch {b}: best p_rmse={best['p_rmse']:.2f} @ mux={best['mux']} mup={best['mup']} yield={best['yield_err']:+.1%} co2d={best['co2d']}"
    if good:
        g = min(good, key=lambda r: r["p_rmse"])
        bmsg += f" | best-in-band: p_rmse={g['p_rmse']:.2f} @ ({g['mux']},{g['mup']}) yield={g['yield_err']:+.1%} co2d={g['co2d']}"
    print(bmsg, flush=True)

with open("runs/b80_92_rescue_scan.json", "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print("Saved: runs/b80_92_rescue_scan.json")

# -*- coding: utf-8 -*-
"""批 92 mup 零交叉扫描：stage-1 (mup~0.010) 给 -95.8%，mup=0.041 给 +86%
→ 零交叉在 0.010-0.041 之间，此前网格（0.041-0.070）恰好漏掉。
在零交叉邻域找 P_offline 拟合最优的 mup。
"""
import sys, os, json
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from simulate import simulate_open_loop, yield_metrics
from diag_b_stage2 import p_offline_rmse

d = pd.read_csv("data/processed/batches/batch_92.csv")
MUP_GRID = [0.010, 0.015, 0.018, 0.022, 0.026, 0.030, 0.034, 0.038, 0.041]
MUX_GRID = [0.41, 0.47]

rows = []
for mux in MUX_GRID:
    for mup in MUP_GRID:
        params = {"mux": mux, "mup": mup, "m_s": 0.029, "dist_tcin_asym": 18,
                  "alpha_kla": 85.0, "PAA_c": 530000.0, "N_conc_paa": 150000.0,
                  "c_oil": 1000.0, "dist_flag": 1}
        sim, v3 = simulate_open_loop(92, params)
        pr, n = p_offline_rmse(sim, v3)
        ym = yield_metrics(sim, v3)
        rows.append({"mux": mux, "mup": mup, "p_rmse": round(pr, 2),
                     "yield_err": round(ym["rel_err_total"], 4),
                     "co2d": round(sim["CO2d"].max(), 2)})
        print(f"mux={mux} mup={mup:.3f}: p_rmse={pr:5.2f} yield={ym['rel_err_total']:+7.1%} co2d={sim['CO2d'].max():.2f}", flush=True)

with open("runs/b92_crossing_scan.json", "w", encoding="utf-8") as f:
    json.dump(rows, f, ensure_ascii=False, indent=2)
best_fit = sorted(rows, key=lambda r: r["p_rmse"])[0]
best_yield = sorted(rows, key=lambda r: abs(r["yield_err"]))[0]
print(f"\nbest P-fit: {best_fit}\nbest yield: {best_yield}")

# -*- coding: utf-8 -*-
"""批 92 mup 精细交叉扫描（0.030-0.034 之间 6 点，mux 取 0.41 与 0.47）。"""
import sys, os, json
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from simulate import simulate_open_loop, yield_metrics
from diag_b_stage2 import p_offline_rmse

d = pd.read_csv("data/processed/batches/batch_92.csv")
MUP_GRID = [0.0305, 0.0310, 0.0315, 0.0320, 0.0325, 0.0330, 0.0335]
rows = []
for mux in [0.41, 0.47]:
    for mup in MUP_GRID:
        params = {"mux": mux, "mup": mup, "m_s": 0.029, "dist_tcin_asym": 18,
                  "alpha_kla": 85.0, "PAA_c": 530000.0, "N_conc_paa": 150000.0,
                  "c_oil": 1000.0, "dist_flag": 1}
        sim, v3 = simulate_open_loop(92, params)
        pr, _ = p_offline_rmse(sim, v3)
        ym = yield_metrics(sim, v3)
        rows.append({"mux": mux, "mup": mup, "p_rmse": round(pr, 3),
                     "yield_err": round(ym["rel_err_total"], 4),
                     "co2d": round(sim["CO2d"].max(), 2)})
        print(f"mux={mux} mup={mup:.4f}: p_rmse={pr:5.2f} yield={ym['rel_err_total']:+7.2%} co2d={sim['CO2d'].max():.2f}", flush=True)

with open("runs/b92_crossing_fine.json", "w", encoding="utf-8") as f:
    json.dump(rows, f, ensure_ascii=False, indent=2)
inband = [r for r in rows if abs(r["yield_err"]) <= 0.05]
print(f"\nwithin ±5%: {len(inband)} -> {inband[:4] if inband else 'none'}")

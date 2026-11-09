# -*- coding: utf-8 -*-
"""B 档联合二阶段：mup × m_s 2D 扫描，目标 = P_offline RMSE + 在线 RMSE 联合。

先验（stage-1 结果）：批 80/92 的 mux/dTcin 在线拟合偏差大，单维 mup 无法救 →
在 P_offline 锚定下联合微调 m_s（第一阶段在线目标欠定的补偿项）。
"""
import sys, os, json
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from simulate import simulate_open_loop, yield_metrics
from soft_sensing import online_rmse
from diag_b_stage2 import p_offline_rmse

BATCHES = [16, 36, 80, 92]
MUP_GRID = [0.030, 0.041, 0.050, 0.060, 0.070]
MS_GRID = [0.015, 0.020, 0.025, 0.029]
# 基参数取自 stage-1 各批（不含 mup/m_s 会被覆盖）
S1 = {16: {"mux": 0.35, "dist_tcin_asym": 15}, 36: {"mux": 0.35, "dist_tcin_asym": 10},
      80: {"mux": 0.35, "dist_tcin_asym": 20}, 92: {"mux": 0.47, "dist_tcin_asym": 10}}

results = []
for b in BATCHES:
    d = pd.read_csv(f"data/processed/batches/batch_{b:02d}.csv")
    rows = []
    for mup in MUP_GRID:
        for ms in MS_GRID:
            params = dict(S1[b], mup=mup, m_s=ms, alpha_kla=85.0,
                          PAA_c=530000.0, N_conc_paa=150000.0, c_oil=1000.0,
                          dist_flag=1)
            sim, v3 = simulate_open_loop(b, params)
            pr, n = p_offline_rmse(sim, v3)
            on = online_rmse(sim, v3)
            co2d = sim["CO2d"].max()
            joint = 0.5 * (pr / 10.0) + 0.5 * on * (10.0 if co2d <= 7.57 else 30.0)
            rows.append({"mup": mup, "m_s": ms, "p_rmse": round(pr, 2),
                         "online": round(on, 3), "joint": round(joint, 3),
                         "co2d": round(co2d, 2)})
    best = min(rows, key=lambda r: r["joint"])
    params = dict(S1[b], mup=best["mup"], m_s=best["m_s"], alpha_kla=85.0,
                  PAA_c=530000.0, N_conc_paa=150000.0, c_oil=1000.0, dist_flag=1)
    sim, _ = simulate_open_loop(b, params)
    ym = yield_metrics(sim, d)
    results.append({"batch": b, "best": best, "joint_rows": len(rows),
                    "yield_err": float(ym["rel_err_total"]),
                    "co2d_max": float(sim["CO2d"].max()), "scan": rows})
    print(f"batch {b:2d}: best mup={best['mup']:.3f} m_s={best['m_s']:.3f} "
          f"joint={best['joint']:.3f} p_rmse={best['p_rmse']:.2f} "
          f"yield_err={ym['rel_err_total']:+.1%} CO2d={sim['CO2d'].max():.2f}"
          f"{' CRASH' if sim['CO2d'].max() > 7.57 else ''}", flush=True)

with open("runs/soft_sensing_stage2b.json", "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2, default=str)
print("Saved: runs/soft_sensing_stage2b.json")

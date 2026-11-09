# -*- coding: utf-8 -*-
"""Batch 23: 晚期 m_s 上调扫描 — 目标：CO2d ≤ 7.57 且产率 |err| ≤ 5%。

依据：m_s↔CO2d 耦合（高 m_s 晚期少长菌多烧底物 → CO2d 降低）。
 crackdown 发生在 t≈260（批末 264h），V3 X_offline 同期也在衰减（25→22.5），属于自然衰亡期。
"""
import sys, os
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from simulate import simulate_open_loop, yield_metrics

d = pd.read_csv("data/processed/batches/batch_23.csv")

BASE = {"mux": 0.35, "mup": 0.070, "alpha_kla": 85.0,
        "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0,
        "dist_flag": 1, "dist_tcin_asym": 10}

print("=== Batch 23: late m_s up-shift scan (ms_early=0.029) ===", flush=True)
T_GRID = [200, 220, 240]
MS_LATE = [0.030, 0.032, 0.035, 0.038, 0.042]

best = None
for t_sw in T_GRID:
    for ms_late in MS_LATE:
        params = dict(BASE, **{"m_s": 0.029, "m_s_schedule": [(t_sw, ms_late)]})
        sim, _ = simulate_open_loop(23, params)
        ym = yield_metrics(sim, d)
        err = ym["rel_err_total"]
        co2d = sim["CO2d"].max()
        ph_end = sim["pH"].iloc[-1]
        status = "CRASH" if co2d > 7.57 else "ok"
        tag = ""
        if co2d <= 7.57 and abs(err) <= 0.05:
            tag = " <== PASS"
            if best is None or abs(err) < abs(best["err"]):
                best = {"err": err, "t_sw": t_sw, "ms_late": ms_late, "co2d": co2d}
        print(f"  t_sw={t_sw:3d} ms_late={ms_late:.3f}: yield={err:+.1%} CO2d={co2d:.2f} pH_end={ph_end:.2f} {status}{tag}", flush=True)

# 基线（无时变）
sim, _ = simulate_open_loop(23, dict(BASE, m_s=0.029))
ym = yield_metrics(sim, d)
print(f"\n  baseline (no schedule): yield={ym['rel_err_total']:+.1%} CO2d={sim['CO2d'].max():.2f}")
if best:
    print(f"  BEST PASS: t_sw={best['t_sw']} ms_late={best['ms_late']:.3f} yield={best['err']:+.1%} CO2d={best['co2d']:.2f}")

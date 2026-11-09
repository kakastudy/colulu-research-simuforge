# -*- coding: utf-8 -*-
"""R130e: 批 22 真实 BDF 轨迹解剖 —— 从 simulate_open_loop 输出提取关键变量。"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from simulate import simulate_open_loop  # noqa: E402

B = 22
PARAMS = {"mux": 0.35, "mup": 0.065, "dist_tcin_asym": 20, "m_s": 0.029,
          "m_s_schedule": [(110, 0.010)], "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40,
          "alpha_kla": 85, "mu_h_scale": 3.5}

sim, v3 = simulate_open_loop(B, params=PARAMS)

keys = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 110, 120, 130, 140, 150, 160, 170, 180, 190, 200, 210, 220, 230]
print(f"{'t':>6s} {'S':>8s} {'X':>7s} {'P':>7s} {'A0':>6s} {'A1':>6s} {'A3':>6s} {'A4':>6s} {'mux':>7s} {'pH':>6s} {'CO2d':>6s}")
for kk in keys:
    sub = sim[(sim['time_h'] >= kk) & (sim['time_h'] < kk + 5)]
    if len(sub) == 0:
        continue
    r = sub.iloc[len(sub) // 2]
    print(f"{r['time_h']:6.1f} {r['S']:8.3f} {r['X']:7.2f} {r['P']:7.3f} "
          f"{r['A0']:6.2f} {r['A1']:6.2f} {r['A3']:6.2f} {r['A4']:6.2f} "
          f"{r['mux']:7.4f} {r['pH']:6.2f} {r['CO2d']:6.2f}")

# V3 对照
print("\n--- V3 对照 ---")
v3x = pd.to_numeric(v3["X_offline"], errors="coerce")
print(f"{'t':>6s} {'S_v3':>8s} {'X_off':>7s} {'P_v3':>7s}")
for kk in keys:
    sub = v3[(v3['time_h'] >= kk) & (v3['time_h'] < kk + 5)]
    if len(sub) == 0:
        continue
    r = sub.iloc[len(sub) // 2]
    print(f"{r['time_h']:6.1f} {r['S']:8.3f} {r['X_offline'] if pd.notna(r['X_offline']) else -1:7.2f} {r['P']:7.3f}")

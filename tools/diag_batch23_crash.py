# -*- coding: utf-8 -*-
"""Batch 23 崩溃诊断：
1) sim 在何时何处 CO2d 穿越 7.57？之后 mu_e/P/pH 发生什么？
2) V3 batch 23 末段 X/P/pH 行为对照 — V3 是否也显示生长停滞？
3) 用 V3 尾气 + 呼吸商做碳平衡变换，反推 V3 隐含的 CO2 生成速率轨迹。
"""
import sys, os
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from simulate import simulate_open_loop

d = pd.read_csv("data/processed/batches/batch_23.csv")
params = {"mux": 0.35, "mup": 0.070, "alpha_kla": 85.0,
          "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0,
          "dist_flag": 1, "dist_tcin_asym": 10, "m_s": 0.029}
sim, _ = simulate_open_loop(23, params)

# 合并到共同时间轴
m = pd.merge_asof(sim[["time_h", "CO2d", "P", "pH", "X", "A0", "S", "mu_e"]] if "X" in sim.columns
                  else sim[["time_h", "CO2d", "P", "pH", "S"]],
                  d[["time_h", "P_offline", "X_offline", "pH", "P", "S"]],
                  on="time_h", direction="nearest", tolerance=0.21,
                  suffixes=("_sim", "_v3"))

print("=== Batch 23 sim CO2d 穿越 7.57 的时点 ===")
cr = sim[sim["CO2d"] > 7.57]
if len(cr):
    print(f"  first crossing: t={cr['time_h'].iloc[0]:.1f} h ; 最后时段 CO2d max={sim['CO2d'].max():.2f}")
    t0 = cr["time_h"].iloc[0]
    post = sim[sim["time_h"] >= t0]
    print(f"  crossing 后时长: {post['time_h'].iloc[-1]-t0:.1f} h / 总批次 {sim['time_h'].iloc[-1]:.1f} h")
    # mu_e 不在输出列则跳过
    for ch in ["P", "pH", "S", "A0"]:
        if ch in sim.columns:
            print(f"  P: {sim[sim['time_h']==t0][ch].iloc[0] if len(sim[sim['time_h']==t0]) else '?'} → {post[ch].iloc[-1]:.2f} ({ch})")
else:
    print("  no crossing?? max CO2d =", sim["CO2d"].max())

print("\n=== 末段对照 (t>180h): sim vs v3 ===")
tail = m[m["time_h"] > 180]
cols = [c for c in ["time_h", "CO2d", "P_sim", "P_offline", "P_v3", "X_offline", "pH_sim", "pH_v3", "S_sim", "S_v3"] if c in tail.columns]
print(tail[cols].to_string(index=False, float_format=lambda v: f"{v:8.2f}"))

# -*- coding: utf-8 -*-
"""估算 backward-looking Fs 步骤的累积底物误差。"""
import pandas as pd

v3 = pd.read_csv("data/processed/batches/batch_01.csv")
Fs = v3["Fs"].values
t = v3["time_h"].values
V = v3["V"].values
c_s = 600.0

# 计算每个间隔的 Fs 误差
total_error = 0.0
for i in range(1, len(Fs)):
    dt = t[i] - t[i-1]
    # sim 使用 Fs[i] (t_sample) 驱动 [t[i-1], t[i]]
    # 实际 Fs 在 [t[i-1], t[i]] 是 Fs[i-1]
    sim_input = Fs[i] * c_s / V[i-1] * dt  # sim 的底物输入
    actual_input = Fs[i-1] * c_s / V[i-1] * dt  # 实际底物输入
    error = sim_input - actual_input
    total_error += error
    if abs(error) > 0.01:
        print(f"t={t[i]:.1f}: Fs {Fs[i-1]:.0f}->{Fs[i]:.0f}, dt={dt:.1f}, error={error:.4f} g/L")

print(f"\n总 Fs 步骤误差: {total_error:.4f} g/L")
print(f"对应生物量误差: {total_error/1.85:.4f} g/L")
print(f"sim X@196 = 31.5, V3 X@196 ≈ 23.4, 差异 = 8.1 g/L")
print(f"Fs 误差占差异的 {total_error/1.85/8.1*100:.1f}%")

# -*- coding: utf-8 -*-
"""透明追踪：批 11 死亡项修正的逐化验点 A_t1/encoding 值（消除量纲疑云）。"""
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="gbk", errors="replace")
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "candidate", "indpensim", "v0.1"))

import numpy as np
import pandas as pd
from simulate import simulate_open_loop
from calibration import calib_params
from observe import load_death_coef, _death_corr

coef = load_death_coef()
sim, v3 = simulate_open_loop(11, calib_params(11))
t = sim["time_h"].to_numpy(float)
at1_rec = sim["A_t1"].to_numpy(float)  # 记录列
a0 = sim["A0"].to_numpy(float)
den = (sim["A1"] + sim["A3"] + sim["A4"]).to_numpy(float)
at1_ca = a0 / np.maximum(den, 1e-9)  # 公式口径
Xcorr = _death_corr(sim, coef)
X = sim["X"].to_numpy(float)

po = pd.to_numeric(v3["X_offline"], errors="coerce")
print("t_lab-4  at1_rec   at1_formula   X      X_corr   X_off")
for i, v in po.items():
    if not np.isfinite(v):
        continue
    tl = float(v3.loc[i, "time_h"])
    if tl - 4 < 20:
        continue
    j = int(np.argmin(np.abs(t - (tl - 4))))
    print(f"{tl:7.1f} {at1_rec[j]:8.1f} {at1_ca[j]:10.2e} {X[j]:7.2f} {Xcorr[j]:8.2f} {v:6.2f}")

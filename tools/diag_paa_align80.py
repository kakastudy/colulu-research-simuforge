# -*- coding: utf-8 -*-
"""批 80 引擎 PAA vs V3 PAA_offline 对齐诊断（量纲/滞后/散点）。"""
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

sim, v3 = simulate_open_loop(int(sys.argv[1]) if len(sys.argv) > 1 else 80, calib_params(int(sys.argv[1]) if len(sys.argv) > 1 else 80))
ts = sim["time_h"].to_numpy(float)
eng = sim["PAA"].to_numpy(float)
lab = pd.to_numeric(v3["PAA_offline"], errors="coerce").to_numpy(float)
t_lab = v3["time_h"].to_numpy(float)

print("engine PAA: min %.3f max %.3f end %.3f" % (eng.min(), eng.max(), eng[-1]))
print("engine P 维持峰 %.1f; V=%.0f" % (sim["P"].max(), sim["V"].iloc[-1]))
pts = [(float(t), float(v)) for i, (t, v) in enumerate(zip(t_lab, lab))
       if np.isfinite(v) and t > 20][:12]
print("t_lab,  v3_assay,  eng(t),  eng(t-4), eng(t+4)")
for t, v in pts:
    e0 = float(np.interp(t, ts, eng))
    em = float(np.interp(t - 4, ts, eng))
    ep = float(np.interp(t + 4, ts, eng))
    print(f"{t:6.1f}  {v:7.3f}  {e0:7.3f}  {em:7.3f}  {ep:7.3f}")
for lag in (0, 2, 4, 6, 8, 12):
    pairs = [(np.interp(t - lag, ts, eng), v) for t, v in pts]
    a = np.array(pairs)
    print(f"lag={lag:2d}h r={np.corrcoef(a[:, 0], a[:, 1])[0, 1]:+.3f} "
          f"scale med={np.median(a[:, 0] / np.maximum(np.abs(a[:, 1]), 1e-6)):+.1f}x")

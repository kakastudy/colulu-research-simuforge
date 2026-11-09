# -*- coding: utf-8 -*-
"""诊断：基线引擎 vs EnKF 状态（X/S/P 逐段打印）。"""
import sys, os
sys.path.insert(0, 'candidate/indpensim/v0.1')
import numpy as np
from simulate import simulate_open_loop
from calibration import calib_params

sim, v3 = simulate_open_loop(11, calib_params(11))
t_sim = sim['time_h'].to_numpy(float)
print("=== 基线引擎（校准参数）关键时点 ===")
for tt in (40, 80, 120, 160, 200, 240):
    i = (abs(t_sim - tt) < 0.11)
    r = sim[i]
    if len(r):
        print(f"t={tt}: X={r['X'].iloc[0]:.2f} S={r['S'].iloc[0]:.3f} P={r['P'].iloc[0]:.2f} mup_state={r['mup'].iloc[0]:.3f}")

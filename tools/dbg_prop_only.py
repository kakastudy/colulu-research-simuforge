# -*- coding: utf-8 -*-
"""二分诊断：成员仅推进（无同化）X 轨迹 vs 基线引擎 X 轨迹。"""
import sys, os
sys.path.insert(0, 'candidate/indpensim/v0.1')
import numpy as np
from simulate import integrate_interval, guards, build_inp1, load_batch, build_initial_state, simulate_open_loop, make_params
from calibration import calib_params

params = calib_params(11)
par_base = make_params(alpha_kla=85.0, mup=params["mup"], mux=params["mux"],
                       N_conc_paa=150000.0, PAA_c=530000.0, c_oil=1000.0)
par_base[24] = params["m_s"]
d = load_batch(11)
y0 = build_initial_state(d)

y = y0.copy()
mv_row = d.iloc[0]
t_current = d['time_h'].iloc[0]
print("=== 逐区间推进（无同化，par_base 即批次校准参数）===")
marks = {40, 80, 120, 160, 200, 240}
for i in range(1, len(d)):
    row = d.iloc[i]
    t_sample = float(row['time_h'])
    if t_sample <= t_current:
        continue
    inp1 = build_inp1(mv_row, inhib=2, dist_flag=1, dist_tcin=10.0)
    y = integrate_interval(t_current, y, inp1, par_base)
    y = guards(y)
    t_current = t_sample
    mv_row = row
    tt = round(t_sample)
    if any(abs(tt - m) <= 0 for m in marks):
        X_sum = y[11] + y[12] + y[13] + y[14]
        print(f"t={tt}: X_comps=({y[11]:.3f},{y[12]:.3f},{y[13]:.3f},{y[14]:.3f}) sum={X_sum:.2f} S={y[0]:.4f} P={y[3]:.2f}")

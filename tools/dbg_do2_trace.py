# -*- coding: utf-8 -*-
"""DO2 单通道早期追踪：每 2h 间隔打印成员 X/S/DO2/pH_H —— 观测同化后的实际变化。"""
import sys
sys.path.insert(0, 'candidate/indpensim/v0.1')
import numpy as np
from simulate import integrate_interval, guards, build_inp1, load_batch, build_initial_state, IDX
from calibration import calib_params
import observe as ob

params = calib_params(11)
par_base = ob.make_params(alpha_kla=85.0, mup=params["mup"], mux=params["mux"],
                          N_conc_paa=150000.0, PAA_c=530000.0, c_oil=1000.0) if hasattr(ob, 'make_params') else None
from simulate import make_params
par_base = make_params(alpha_kla=85.0, mup=params["mup"], mux=params["mux"],
                       N_conc_paa=150000.0, PAA_c=530000.0, c_oil=1000.0)
par_base[24] = params["m_s"]
d = load_batch(11)
y0 = build_initial_state(d)
rng = np.random.default_rng(7)
y_ens, thetas = ob._initial_ensemble(y0, params, 20, rng)
n = 33
z = np.column_stack([y_ens, thetas["mup"], thetas["m_s"]])

mv_row = d.iloc[0]
t_cur = float(d['time_h'].iloc[0])
for i in range(1, len(d)):
    row = d.iloc[i]
    t_s = float(row['time_h'])
    if t_s <= t_cur:
        continue
    inp1 = build_inp1(mv_row, inhib=2, dist_flag=1, dist_tcin=10.0)
    for e in range(20):
        par = par_base.copy()
        par[0] = z[e, n]; par[24] = z[e, n + 1]
        try:
            z[e, :n] = integrate_interval(t_cur, z[e, :n], inp1, par)
            z[e, :n] = guards(z[e, :n])
        except Exception:
            z[e, :n] = z.mean(0)[:n] + rng.normal(0, 1e-2, n)
    obs = {}
    val = float(row['DO2'])
    if np.isfinite(val) and t_s > 20:
        obs['DO2'] = (IDX['DO2'], val)
    if obs:
        z = ob.enkf_update(z, obs, ob.OBS_R)
    t_cur = t_s
    if abs((t_s % 2) - 0.2) > 0.15 and int(t_s) % 4 == 0:
        Xs = z[:, 11] + z[:, 12] + z[:, 13] + z[:, 14]
        print(f"t={t_s:6.1f} X_mean={Xs.mean():7.2f} S_mean={z[:,0].mean():7.4f} "
              f"DO2_mean={z[:,1].mean():6.1f} (obs {val:5.1f}) pH_H={z[:,6].mean():.2e} "
              f"mup={z[:,33].mean():.4f} ms={z[:,34].mean():.4f}")

# -*- coding: utf-8 -*-
"""批 73 发散根因探针：参数/初始状态/积分哪一环出 NaN。"""
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="gbk", errors="replace")
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "candidate", "indpensim", "v0.1"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import residual_discovery as rd

thetas = rd.load_theta()
th = thetas.get(73)
print("theta keys:", None if th is None else sorted(th.keys())[:12])
try:
    sim, v3, res = rd._aligned_residuals(73, th)
    print("aligned OK; res S points:", len(res["S"]["t"]))
except Exception as e:
    print("aligned FAIL:", type(e).__name__, str(e)[:200])

# 参数回放
from simulate import simulate_open_loop
def params_from(theta):
    keys = ("mux", "mup", "m_s", "dist_tcin_asym", "m_s_schedule", "alpha_kla")
    return {k: theta[k] for k in keys if k in theta}

try:
    sim, v3 = simulate_open_loop(73, params_from(th))
    X = sim["X"].to_numpy(float)
    print("replay OK: X end=%.2f P end=%.2f nan_frac=%.3f" % (
        X[-1], sim["P"].to_numpy(float)[-1], float(np.isnan(X).mean())))
except Exception as e:
    print("replay FAIL:", type(e).__name__, str(e)[:200])

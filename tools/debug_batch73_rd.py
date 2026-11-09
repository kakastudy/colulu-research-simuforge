# -*- coding: utf-8 -*-
"""批 73 rd 路径 vs 直调路径参数等值精查（打印实际 params 与 y0）。"""
import io
import sys
import traceback

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="gbk", errors="replace")
sys.path.insert(0, r"C:\Users\admin\Desktop\AI4S研究\青霉素反应罐\candidate\indpensim\v0.1")
sys.path.insert(0, r"C:\Users\admin\Desktop\AI4S研究\青霉素反应罐\tools")

import residual_discovery as rd

thd = rd.load_theta()
th = thd.get(73)
tp = th["theta_post"]
print("theta_post:", tp)
params = {"mux": tp["mux"], "mup": tp["mup"], "m_s": tp["m_s"], "alpha_kla": 85.0,
          "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0,
          "dist_flag": 1, "dist_tcin_asym": 10}
from simulate import simulate_open_loop, build_initial_state, load_batch
d = load_batch(73)
y0 = build_initial_state(d)
print("y0 finite:", bool(__import__('numpy').isfinite(list(y0)).all()))
try:
    sim, v3 = simulate_open_loop(73, params)
    print("simulate OK")
except Exception:
    print("simulate FAIL:")
    traceback.print_exc()
try:
    res = rd._aligned_residuals(73, th)
    print("aligned OK")
except Exception:
    print("aligned FAIL:")
    traceback.print_exc()

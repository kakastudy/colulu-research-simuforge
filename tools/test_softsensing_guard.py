# -*- coding: utf-8 -*-
"""B 档强化版探测：1 组合小网格 + 发散守卫注错测试；C 档看板引用烟囱。"""
import os, sys
os.environ["DASH_NO_UI"] = "1"
import numpy as np

V01 = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "candidate", "indpensim", "v0.1")
sys.path.insert(0, V01)
import dashboard as db
import soft_sensing as ss

PASS = 0
def ok(name, cond):
    global PASS
    if not cond:
        raise AssertionError(name)
    PASS += 1
    print("[PASS]", name)

# 1) 小网格估算（绝对路径 + 正常路径）
r = ss.estimate_batch(8, verbose=False,
                      grid={"muxs": [0.41], "mups": [0.041], "mss": [0.020], "tcins": [10]},
                      on_progress=lambda d, t: None)
ok("estimate_batch small-grid OK (params returned)", "mux" in r["params"] and r["yield_err"] < 9)

# 2) 发散守卫：注错 simulate_open_loop → 返回劣解不中断
orig = ss.simulate_open_loop
def boom(*a, **k):
    raise RuntimeError("BDF failed at t=... (注入)")
ss.simulate_open_loop = boom
try:
    r2 = ss.estimate_batch(8, verbose=False,
                           grid={"muxs": [0.41], "mups": [0.041], "mss": [0.020], "tcins": [10]})
    ok("diverged combo → 劣解 (online_rmse=1e6), 不抛异常", r2["online_rmse"] >= 1e5 or r2["crashed"])
finally:
    ss.simulate_open_loop = orig

# 3) 看板 B/C 段引用烟囱（不执行 UI，仅确认名称存在）
src = open(os.path.join(V01, "dashboard.py"), encoding="utf-8").read()
ok("dashboard B段: 进度条 + except 保护", "on_progress" in src and "st.error" in src)
ok("dashboard C段: optimize_feed + 目标模式", "optimize_feed" in src and "track_target" in src)

print(f"\nAll {PASS} probes passed")

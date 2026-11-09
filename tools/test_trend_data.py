# -*- coding: utf-8 -*-
"""B/B2/C 趋势数据无头探测：小网格 sweep / stage-2 扫描含 yield 列 / optimize history。"""
import os, sys
V01 = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "candidate", "indpensim", "v0.1")
sys.path.insert(0, V01)
os.environ["DASH_NO_UI"] = "1"
import soft_sensing as ss
import stage2_estimator as s2
import optimize as op
from calibration import calib_params

# 1) B stage-1 小网格（2 组合）→ sweep 含 yield_err
r1 = ss.estimate_batch(8, verbose=False,
                       grid={"muxs": [0.41], "mups": [0.030, 0.041],
                             "mss": [0.020], "tcins": [10]})
assert len(r1["sweep"]) == 2 and "yield_err" in r1["sweep"][0]
print("[PASS] B sweep 有 yield_err:", [(x["mup"], round(x["yield_err"], 3)) for x in r1["sweep"]])

# 2) stage-2 扫描（2 mup）→ scan 含 yield_err
r2 = s2.estimate_stage2(16, calib_params(16), mup_grid=[0.030, 0.060])
assert "yield_err" in r2["scan"][0] and "co2d" in r2["scan"][0]
print("[PASS] B2 scan 有 yield/co2d:", [(x["mup"], round(x["yield_err"], 3), round(x["co2d"], 2)) for x in r2["scan"]])

# 3) C 收敛 history（maxiter 6，1 维）
r3 = op.optimize_feed(8, var_names=["Foil"], maxiter=6, verbose=False)
assert len(r3.get("history")) >= 1 and "history" in r3
print("[PASS] C history:", [(h["eval"], None if h["yield_g"] is None else round(h["yield_g"]/1e6, 3)) for h in r3["history"]][:6])
print("TREND DATA PROBES PASS")

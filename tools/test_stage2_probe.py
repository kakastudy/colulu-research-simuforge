# -*- coding: utf-8 -*-
"""stage2_estimator 无头验证：批 16 小网格（2 mup）走通。"""
import os, sys
V01 = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "candidate", "indpensim", "v0.1")
sys.path.insert(0, V01)
from stage2_estimator import estimate_stage2
from calibration import calib_params

r = estimate_stage2(16, calib_params(16), mup_grid=[0.030, 0.060])
print("stage2 b16:", {k: (round(v, 3) if isinstance(v, (int, float)) else v)
                      for k, v in r.items() if k != "scan"})
print("scan:", [(x["mup"], round(x["p_rmse"], 2)) for x in r["scan"]])
assert r["stage2_mup"] in (0.030, 0.060)
print("STAGE2 PROBE PASS")

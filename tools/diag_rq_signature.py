# -*- coding: utf-8 -*-
"""故障特征级验证（GOAL §4.4 / 待审阅 C2）：sim vs V3 的 RQ 与尾气统计对照。

问题：V3 故障批 91 的 RQ 中位 2.23（正常批 0.89-1.16）——故障注入的
"特征"体现在 V3 气体通道合成层。引擎回放（机理）是否复现该特征？
"""
import sys, os
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from simulate import simulate_open_loop
from calibration import calib_params, GOLDEN

rows = []
for b in GOLDEN:
    sim, v3 = simulate_open_loop(b, calib_params(b))
    def rq(d):
        q = (d["CER"] / np.maximum(abs(d["OUR"]), 1e-9)).replace([np.inf, -np.inf], np.nan).dropna()
        return float(q.median()), float(q.quantile(0.95))
    m3, p3 = rq(v3)
    ms_, ps_ = rq(sim)
    rows.append({"batch": b, "v3_rq_med": m3, "v3_rq_p95": p3,
                 "sim_rq_med": ms_, "sim_rq_p95": ps_,
                 "fault": 1 if b in (91, 92) else 0})
    print(f"batch {b:2d}{'(fault)' if b in (91,92) else ''}: V3 RQ_med={m3:.2f} p95={p3:.2f} | sim RQ_med={ms_:.2f} p95={ps_:.2f}", flush=True)

with open("runs/rq_signature_check.json", "w", encoding="utf-8") as f:
    import json
    json.dump(rows, f, ensure_ascii=False, indent=2)
print("Saved: runs/rq_signature_check.json")

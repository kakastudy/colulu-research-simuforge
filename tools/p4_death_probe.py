# -*- coding: utf-8 -*-
"""P4 v0.2 升级前探针（R44）：死亡项后验修正对黄金批确定性 X 轨迹 RMSE 的净效应。

方法：黄金批逐个确定性重放（calib_params），death-corr 只改 X 通道（_death_corr），
复用 trajectory_metrics 的同一 4h 滞后对齐（X(t-4h) vs X_offline）做 base/corr 双算。
判据（P4 登记流程）：X 轨迹 nRMSE 改善才支持 calibration.py 挂死亡项算子（v0.2 升级），
否则 v0.2 仅限观测层（集合平滑器），引擎不动。
"""
import io
import json
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="gbk", errors="replace")
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "candidate", "indpensim", "v0.1"))

import numpy as np
import pandas as pd

from simulate import simulate_open_loop
from calibration import calib_params, GOLDEN_NORMAL
from trajectory_metrics import trajectory_metrics
from observe import load_death_coef, _death_corr

COEF = load_death_coef()
assert COEF is not None, "runs/hier_est/death_term.json 缺失（PH2 死亡项未产出）"
print("coef:", COEF)

BATCHES = [int(b) for b in (sys.argv[1].split(",") if len(sys.argv) > 1 else GOLDEN_NORMAL)]
results = []
for b in BATCHES:
    sim, v3 = simulate_open_loop(b, calib_params(b))
    m_base = trajectory_metrics(sim, v3)["X_offline"]
    sim_c = sim.copy()
    sim_c["X"] = _death_corr(sim, COEF)
    m_corr = trajectory_metrics(sim_c, v3)["X_offline"]
    row = {
        "batch": b,
        "base": {k: m_base[k] for k in ("rmse", "nrmse_pct", "corr")},
        "death_corr": {k: m_corr[k] for k in ("rmse", "nrmse_pct", "corr")},
        "delta_nrmse_pct": m_corr["nrmse_pct"] - m_base["nrmse_pct"],
    }
    row["base"] = {k: float(v) for k, v in row["base"].items()}
    row["death_corr"] = {k: float(v) for k, v in row["death_corr"].items()}
    row["delta_nrmse_pct"] = float(row["delta_nrmse_pct"])
    results.append(row)
    print(f"batch {b:2d}: X nRMSE {row['base']['nrmse_pct']:5.1f}% -> "
          f"{row['death_corr']['nrmse_pct']:5.1f}%  (delta {row['delta_nrmse_pct']:+5.1f} pt, "
          f"corr {row['base']['corr']:.3f} -> {row['death_corr']['corr']:.3f})", flush=True)

out = os.path.join(ROOT, "runs", "hier_est", "p4_death_probe.json")
os.makedirs(os.path.dirname(out), exist_ok=True)
with open(out, "w", encoding="utf-8") as f:
    json.dump({"coef": COEF, "batches": results}, f, ensure_ascii=False, indent=2)
improved = [r for r in results if r["delta_nrmse_pct"] < 0]
print(f"\nverdict: {len(improved)}/{len(results)} 批 X nRMSE 改善 -> "
      f"{'支持引擎层 v0.2 升级' if len(improved) * 2 >= len(results) else 'v0.2 仅限观测层（引擎不动）'}")
print(f"Saved: {out}")

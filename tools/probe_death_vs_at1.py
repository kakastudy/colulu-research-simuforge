# -*- coding: utf-8 -*-
"""死亡项改善幅度 vs A_t1 培养龄相关的机理解释探针（R48 批 27 疑点的收口）。"""
import io
import json
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="gbk", errors="replace")
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "candidate", "indpensim", "v0.1"))

import numpy as np

from simulate import simulate_open_loop
from calibration import calib_params, GOLDEN_NORMAL
from observe import load_death_coef, _death_corr

probe = json.load(open(os.path.join(ROOT, "runs", "hier_est", "p4_death_probe.json"), encoding="utf-8"))
delta = {r["batch"]: r["delta_nrmse_pct"] for r in probe["batches"]}

rows = []
for b in GOLDEN_NORMAL:
    sim, _ = simulate_open_loop(b, calib_params(b))
    at1 = sim["A_t1"].to_numpy(float)
    t = sim["time_h"].to_numpy(float)
    late = t >= 100
    at1_late = float(np.median(at1[late])) if late.any() else np.nan
    rng = float(np.max(at1) - np.min(at1))
    rows.append((b, at1_late, rng, delta.get(b, np.nan)))
    print(f"batch {b:2d}: A_t1_late_med={at1_late:.3f} range={rng:.3f} delta={delta.get(b, np.nan):+.1f}pt",
          flush=True)

a1 = np.array([r[1] for r in rows])
a2 = np.array([r[2] for r in rows])
d = np.array([r[3] for r in rows])
print(f"\ncorr(delta, A_t1_late_med) = {np.corrcoef(a1, d)[0, 1]:+.3f}")
print(f"corr(delta, A_t1_range)    = {np.corrcoef(a2, d)[0, 1]:+.3f}")
with open(os.path.join(ROOT, "runs", "hier_est", "p4_death_vs_at1.json"), "w", encoding="utf-8") as f:
    json.dump({"rows": [dict(zip(("batch", "at1_late_med", "at1_range", "delta_pct"), r)) for r in rows],
               "corr_late": float(np.corrcoef(a1, d)[0, 1]), "corr_range": float(np.corrcoef(a2, d)[0, 1])},
              f, ensure_ascii=False, indent=2)
print("Saved: runs/hier_est/p4_death_vs_at1.json")

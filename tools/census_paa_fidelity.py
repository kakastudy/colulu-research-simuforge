# -*- coding: utf-8 -*-
"""PAA 通道保真度普查（R90）：10 个正常黄金批逐批 r（lag 扫描最优）+ 建议表。"""
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

rows = []
for b in GOLDEN_NORMAL:
    sim, v3 = simulate_open_loop(b, calib_params(b))
    ts = sim["time_h"].to_numpy(float)
    eng = sim["PAA"].to_numpy(float)
    lab = np.interp(v3["time_h"].to_numpy(float), ts, eng)
    v3sub = pd_check = None
    import pandas as pd
    pv = pd.to_numeric(v3["PAA_offline"], errors="coerce").to_numpy(float)
    tv = v3["time_h"].to_numpy(float)
    ok = np.isfinite(pv) & (tv > 20)
    n = int(ok.sum())
    if n < 4:
        rows.append({"batch": b, "n": n, "note": "insufficient lab points"})
        continue
    v = pv[ok]; tt = tv[ok]
    sd_mu = float(np.std(v) / max(abs(np.mean(v)), 1e-9))
    if sd_mu < 0.02:
        rows.append({"batch": b, "n": n, "sigma_over_mu": round(sd_mu, 4), "degenerate": True})
        print(f"batch {b:2d}: DEGENERATE (σ/μ={sd_mu:.4f}, n={n})", flush=True)
        continue
    best_r, best_lag = None, None
    for lag in (0, 2, 4, 6, 8):
        e = np.interp(tt - lag, ts, eng)
        r = np.corrcoef(e, v)[0, 1]
        if best_r is None or abs(r) > abs(best_r):
            best_r, best_lag = float(r), lag
    rows.append({"batch": b, "n": n, "best_lag_h": best_lag, "r": round(best_r, 3)})
    print(f"batch {b:2d}: r={best_r:+.3f} @lag{best_lag}h (n={n})", flush=True)

out = os.path.join(ROOT, "runs", "hier_est", "paa_fidelity_census.json")
with open(out, "w", encoding="utf-8") as f:
    json.dump(rows, f, ensure_ascii=False, indent=2)
vals = [abs(r["r"]) for r in rows if "r" in r]
print(f"\n|corr| median = {np.median(vals) if vals else float('nan'):.3f}, "
      f"negative-direction batches = {sum(1 for r in rows if 'r' in r and r['r'] < 0)}/{len(vals)}")
print("Saved:", out)

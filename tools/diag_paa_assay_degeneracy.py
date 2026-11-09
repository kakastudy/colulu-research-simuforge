# -*- coding: utf-8 -*-
"""普查：黄金批 PAA_offline 化验列的退化性（σ/μ、n 点、变程）。"""
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="gbk", errors="replace")

import numpy as np
import pandas as pd

for b in (8, 11, 16, 22, 23, 27, 36, 55, 60, 80, 91, 92):
    d = pd.read_csv(f"data/processed/batches/batch_{b:02d}.csv")
    x = pd.to_numeric(d["PAA_offline"], errors="coerce").to_numpy(float)
    ok = np.isfinite(x) & (d["time_h"].to_numpy(float) > 20)
    v = x[ok]
    if len(v) == 0:
        print(f"batch {b:2d}: no lab points")
        continue
    rng = float(v.max() - v.min())
    print(f"batch {b:2d}: n={len(v):3d}  μ={np.mean(v):8.1f}  σ={np.std(v):7.2f}  "
          f"σ/μ={np.std(v)/max(abs(np.mean(v)),1e-6):6.3f}  range={rng:.1f}  "
          f"min={v.min():.1f} max={v.max():.1f}")

# -*- coding: utf-8 -*-
"""P3-m2 演示：引擎侧 PAT 前向通道（path (a) 成品预览）。

口径（诚实三明治）：
  - 引擎状态 → raman_pipeline.synth_batch → predict_paa: 合成+PLS 内部自洽口径
    （合成层以引擎 PAA 作驱动 → vs 引擎 PAA 是回盘口径，不作预测力证据）；
  - PAT 通道 vs V3 PAA_offline（批 80 是 PAT_ref=2 的 Raman 记录批，化验真值在）:
    为跨引擎口径（引擎≈V3）+独立化验 → 半独立评估；
  - 引用 tools/raman_pipeline.py 的独立口径 r=0.8463 作 PLS 预测力上界参考。
产物：runs/p3/raman_pat_batch80.json。
"""
import io
import json
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="gbk", errors="replace")
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "candidate", "indpensim", "v0.1"))

import numpy as np
import pandas as pd

from simulate import simulate_open_loop
from calibration import calib_params
from raman_pipeline import synth_batch, predict_paa

sim, v3 = simulate_open_loop(80, calib_params(80))

def _grid(col_from_sim):
    y = sim[col_from_sim].to_numpy(float)
    return np.clip(y, 0, None)

P_v = _grid("P")
X_v = _grid("X")            # 引擎 A0+A1+A3+A4 多室和
visc_v = _grid("vis")
S_v = _grid("S")
PAA_e = _grid("PAA")        # 引擎 PAA 状态（g/L）

spec = synth_batch(P_v, X_v, visc_v, S_v, PAA_e)
paa_pat = predict_paa(spec)

# 内部自洽口径：PAT vs 引擎 PAA
r_self = np.corrcoef(paa_pat, PAA_e)[0, 1]
# 跨引擎口径：PAT vs V3 化验（4h 滞后精调——PAT 预测的是采样时刻状态）
lab = pd.to_numeric(v3["PAA_offline"], errors="coerce").to_numpy(float)
t_lab = v3["time_h"].to_numpy(float)
rows = []
for i, v in enumerate(lab):
    if not np.isfinite(v) or t_lab[i] <= 20:
        continue
    j = int(np.argmin(np.abs(sim["time_h"].to_numpy(float) - (t_lab[i] - 4.0))))
    rows.append((paa_pat[j], PAA_e[j], float(v)))
arr = np.array(rows)
r_lab_pat = np.corrcoef(arr[:, 0], arr[:, 2])[0, 1]
r_lab_eng = np.corrcoef(arr[:, 1], arr[:, 2])[0, 1]

out = {
    "batch": 80, "n_spectra": int(spec.shape[1]), "n_lab_points": len(rows),
    "r_self_pat_vs_enginePAA": round(float(r_self), 4),
    "r_lab_pat_vs_v3assay": round(float(r_lab_pat), 4),
    "r_lab_enginePAA_vs_v3assay": round(float(r_lab_eng), 4),
    "note": "引擎直对化验 r(self) 是 PAT 跨引擎口径的上界参照; PLS 独立预测力参考 r=0.8463 (V2 demo)",
    "samples": arr[:24].round(3).tolist(),
}
os.makedirs(os.path.join(ROOT, "runs", "p3"), exist_ok=True)
with open(os.path.join(ROOT, "runs", "p3", "raman_pat_batch80.json"), "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print(json.dumps({k: v for k, v in out.items() if k != "samples"}, ensure_ascii=False, indent=2))

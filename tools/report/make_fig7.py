# -*- coding: utf-8 -*-
"""图 7（单独）：C 档收敛曲线（批 60 track_target，带 history 的新记录）。"""
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)
ASSETS = "runs/report_assets"
plt.rcParams.update({
    "font.sans-serif": ["Microsoft YaHei", "SimHei", "DejaVu Sans"],
    "axes.unicode_minus": False, "font.size": 10.5,
    "savefig.dpi": 220, "axes.grid": True, "grid.alpha": 0.3, "legend.frameon": False,
})

with open("runs/opt_batch_60_track_v2.json", encoding="utf-8") as f:
    r7 = json.load(f)
TARGET = r7["opt_err_vs_v3"] * 0 + 2.379e6  # V3 目标产量 (g)
hist = pd.DataFrame(r7["history"]).dropna(subset=["yield_g"]).set_index("eval")
gap = (hist["yield_g"] - TARGET).abs()
best_gap = gap.cummin()
best_yield = pd.Series(index=hist.index, dtype=float)
for i, ev in enumerate(hist.index):
    seg = gap.loc[:ev]
    best_yield.loc[ev] = hist.loc[seg.idxmin(), "yield_g"]
fig, ax = plt.subplots(figsize=(7.2, 4.0))
ax.plot(hist.index, hist["yield_g"] / 1e6, "o-", ms=4, color="#1f77b4", label="每次评估产量")
ax.plot(best_yield.index, best_yield / 1e6, "-", color="#2ca02c", lw=2.0, label="累计最优（离目标最近）")
ax.axhline(2.379, color="#d62728", ls="--", lw=1.4, label="V3 目标 2.379 Mg")
ax.set_xlabel("评估序号")
ax.set_ylabel("产量 (Mg)")
ax.set_title(f"图 7  C 档收敛曲线（批 60，Fs/Foil，track_target；对 V3 偏差 {r7['opt_err_vs_v3'] * 100:+.2f}%，"
             f"{r7['n_evals']} 次评估）")
ax.legend()
fig.tight_layout()
fig.savefig(os.path.join(ASSETS, "fig7_c_convergence.png"), bbox_inches="tight")
print("fig7 done (track_target-aware best line)")

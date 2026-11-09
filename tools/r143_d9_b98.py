# -*- coding: utf-8 -*-
"""R143 · D-9 交叉验证：b98（从未标为故障批）是否复现同一签名。

b98 在 `GOLDEN_NORMAL` 里，但源数据与 b92 出现**同一时段同一形状**的碱流饱和：
`Fb 141–159 恒 10.00` → `162 跳 225.00`，化验 pH 最低 5.602 @ t=160。

若标称模型（`fault_type=0`）也能复现 b98 的凹陷，则 b92 的"故障"就不是孤例，
而是数据集里**可重复的控制通道事件**。

两臂：基线 / 反事实（窗内 Fb 钉回故障前中位）。不改引擎，monkeypatch `simulate.load_batch`。
"""
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))

import numpy as np
import pandas as pd

import simulate as S
from simulate import simulate_open_loop, yield_metrics
import golden_params as gp

B = 98
WIN = (141.0, 159.0)
OUT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "runs", "p3", "r143_d9_b98.json"))
_ORIG = S.load_batch


def run(fb_level=None):
    def patched(n):
        d = _ORIG(n).copy()
        if fb_level is not None and n == B:
            m = (d["time_h"] >= WIN[0]) & (d["time_h"] <= WIN[1])
            d.loc[m, "Fb"] = float(fb_level)
        return d

    S.load_batch = patched
    try:
        return simulate_open_loop(B, gp.params_for(B))[0]
    finally:
        S.load_batch = _ORIG


def score(sim, d):
    t = d["time_h"].to_numpy(float)
    ta = t - 4.0
    lab = pd.to_numeric(d["pH"], errors="coerce").to_numpy(float)
    ts = sim["time_h"].to_numpy(float)
    ph = sim["pH"].to_numpy(float)
    m = (t >= WIN[0]) & (t <= WIN[1] + 1) & np.isfinite(lab)
    sv = np.interp(ta[m], ts, ph)
    return {
        "rmse_pH_win": float(np.sqrt(np.mean((sv - lab[m]) ** 2))),
        "ph_min_sim_win": float(sv.min()),
        "ph_min_lab_win": float(lab[m].min()),
        "yield_err": float(yield_metrics(sim, d)["rel_err_total"]),
        "ph_end": float(ph[-1]),
    }


def main():
    d = _ORIG(B)
    pre = d[(d["time_h"] >= 125) & (d["time_h"] < WIN[0])]["Fb"]
    fb_pre = float(pre.median())
    rec = {"batch": B, "window": list(WIN), "fb_pre_median": fb_pre, "arms": {}}
    for name, fb in (("A_baseline", None), ("B_fb_counterfactual", fb_pre)):
        rec["arms"][name] = score(run(fb), d)
    json.dump(rec, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=float)

    print(f"b98 · 窗 {WIN[0]:.0f}–{WIN[1]:.0f}h · 故障前 Fb 中位 {fb_pre:.1f}")
    for k, s in rec["arms"].items():
        print(f"  {k:>22} 窗内 pH RMSE {s['rmse_pH_win']:.3f}  sim最低 {s['ph_min_sim_win']:.3f} "
              f"(化验 {s['ph_min_lab_win']:.3f})  yield {s['yield_err']*100:+.2f}%  pH末 {s['ph_end']:.2f}")
    print(f"落盘 {OUT}")


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""R143 · D-9 第二步：b92 pH 事件的机制归属 + 故障算子证伪。

R143a 已证明两件事：
  ① 旧扫描的 mag 量纲错到 2.4e4 倍（等价 mag ≈ 4.2e-3，旧扫描 100–1000）；
  ② 旧扫描的故障窗错位（扫描 40–100h，数据事件在 141–168h）。

本节回答更关键的问题：**b92 到底需不需要"故障注入"这个算子**。
三条臂 + 一条剂量响应：

  A 基线        —— 输入轨迹原样回放
  B 反事实      —— 把故障窗内的 Fb（碱流）钉到故障前水平，其余不动
  C 旧口径故障  —— fault_type=2, window=观测窗, mag=100（台账里"必崩"的那一档）
  D 剂量响应    —— fault_type=2, window=观测窗, mag 从 1e-5 扫到 1e2

判据：
  · 若 B 臂凹陷消失而 A 臂凹陷保留 ⇒ 凹陷由 **Fb 执行器饱和**驱动，不是未知扰动，
    故障算子不但不必要，任何正幅值都是额外误差。
  · 若 D 曲线在 mag→0 处最优且单调恶化 ⇒ 最优"故障幅值"= 0，"重标"的正确解是撤销。

不改引擎；B 臂通过工具内 monkeypatch `simulate.load_batch` 实现。
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

OUT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "runs", "p3", "r143_d9_mechanism.json"))

B = 92
WIN = (141.2, 167.6)
_ORIG_LOAD = S.load_batch


def _patched_load(batch_no, fb_level=None, win=WIN):
    """把故障窗内的 Fb 替换为 fb_level（钳到故障前水平）。"""
    d = _ORIG_LOAD(batch_no).copy()
    if fb_level is not None and batch_no == B:
        m = (d["time_h"] >= win[0]) & (d["time_h"] <= win[1])
        d.loc[m, "Fb"] = float(fb_level)
    return d


def score(sim, d, win=WIN):
    t_sim = sim["time_h"].to_numpy(float)
    t_lab = pd.to_numeric(d["time_h"], errors="coerce").to_numpy(float)
    t_al = t_lab - 4.0
    out = {}
    for ch in ("pH", "S", "P", "DO2"):
        lab = pd.to_numeric(d[ch], errors="coerce").to_numpy(float)
        m = (t_lab > 20) & (t_lab < 260) & np.isfinite(lab)
        sv = np.interp(t_al[m], t_sim, sim[ch].to_numpy(float))
        out["rmse_" + ch] = float(np.sqrt(np.mean((sv - lab[m]) ** 2)))
    # 凹陷窗
    lab_ph = pd.to_numeric(d["pH"], errors="coerce").to_numpy(float)
    m = (t_lab >= win[0]) & (t_lab <= win[1]) & np.isfinite(lab_ph)
    sv = np.interp(t_al[m], t_sim, sim["pH"].to_numpy(float))
    out["rmse_pH_win"] = float(np.sqrt(np.mean((sv - lab_ph[m]) ** 2)))
    out["ph_min_sim_win"] = float(np.min(np.interp(t_sim[(t_sim >= win[0]) & (t_sim <= win[1])],
                                                  t_sim, sim["pH"].to_numpy(float))))
    out["ph_min_lab_win"] = float(np.min(lab_ph[m]))
    # 尾段（t>210）pH 表现 —— 独立缺陷，单列
    mt = (t_lab > 210) & np.isfinite(lab_ph)
    if mt.sum():
        svt = np.interp(t_al[mt], t_sim, sim["pH"].to_numpy(float))
        out["rmse_pH_tail"] = float(np.sqrt(np.mean((svt - lab_ph[mt]) ** 2)))
        out["ph_end_sim"] = float(sim["pH"].iloc[-1])
        out["ph_end_lab"] = float(lab_ph[mt][-1])
    ym = yield_metrics(sim, d)
    out["yield_err"] = float(ym["rel_err_total"])
    out["PHI"] = float("nan")
    return out


def run(fb_level=None, fault=None):
    S.load_batch = lambda b: _patched_load(b, fb_level)
    try:
        p = dict(gp.params_for(B))
        if fault:
            p.update(fault)
        sim, _ = simulate_open_loop(B, p)
    finally:
        S.load_batch = _ORIG_LOAD
    return sim


def main():
    d = _ORIG_LOAD(B)
    rec = {"batch": B, "window": list(WIN), "arms": {}, "dose": []}

    # 故障前 Fb 水平（用于反事实臂）
    pre = d[(d.time_h >= 130) & (d.time_h < WIN[0])]["Fb"]
    fb_pre = float(pre.median())
    rec["fb_pre_median"] = fb_pre
    rec["fb_in_window"] = {
        "min": float(d[(d.time_h >= WIN[0]) & (d.time_h <= WIN[1])]["Fb"].min()),
        "max": float(d[(d.time_h >= WIN[0]) & (d.time_h <= WIN[1])]["Fb"].max()),
        "median": float(d[(d.time_h >= WIN[0]) & (d.time_h <= WIN[1])]["Fb"].median()),
    }

    sims = {
        "A_baseline": run(),
        "B_fb_counterfactual": run(fb_level=fb_pre),
        "C_old_scale_mag100": run(fault={"fault_type": 2, "fault_start": WIN[0],
                                         "fault_end": WIN[1], "fault_magnitude": 100.0}),
    }
    for k, sim in sims.items():
        rec["arms"][k] = score(sim, d)

    # D 剂量响应
    for mag in (0.0, 1e-5, 1e-4, 3e-4, 1e-3, 3e-3, 1e-2, 3e-2, 1e-1, 1.0, 10.0, 100.0):
        if mag == 0.0:
            sim = sims["A_baseline"]
        else:
            sim = run(fault={"fault_type": 2, "fault_start": WIN[0],
                             "fault_end": WIN[1], "fault_magnitude": mag})
        s = score(sim, d)
        rec["dose"].append({"mag": mag, **{k: s[k] for k in
                                          ("rmse_pH_win", "ph_min_sim_win", "rmse_pH", "yield_err")}})
        print(f"  mag={mag:>8.4g}  pH_win {s['rmse_pH_win']:.3f}  pHmin {s['ph_min_sim_win']:.3f}  "
              f"pH_all {s['rmse_pH']:.3f}  yield {s['yield_err']*100:>7.2f}%", flush=True)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(rec, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=float)

    print()
    print("=" * 92)
    print(f"b92 · 故障窗 {WIN[0]:.1f}–{WIN[1]:.1f}h · 故障前 Fb 中位 {fb_pre:.1f} mL/h · "
          f"窗内 Fb {rec['fb_in_window']['min']:.1f}–{rec['fb_in_window']['max']:.1f}")
    print("=" * 92)
    hdr = (f"{'arm':>22} {'pH_min_sim':>10} {'pH_min_lab':>10} {'rmse_pH_win':>11} "
           f"{'rmse_pH':>8} {'rmse_S':>7} {'yield%':>7} {'pH_end':>7}")
    print(hdr)
    for k, s in rec["arms"].items():
        print(f"{k:>22} {s['ph_min_sim_win']:>10.3f} {s['ph_min_lab_win']:>10.3f} "
              f"{s['rmse_pH_win']:>11.3f} {s['rmse_pH']:>8.3f} {s['rmse_S']:>7.2f} "
              f"{s['yield_err']*100:>7.2f} {s.get('ph_end_sim', float('nan')):>7.3f}")
    print(f"\n落盘 {OUT}")


if __name__ == "__main__":
    main()

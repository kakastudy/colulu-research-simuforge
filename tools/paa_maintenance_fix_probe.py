# -*- coding: utf-8 -*-
"""R123: D9(b) PAA 维护消耗修复探查——m_PAA 目标变量 P→total_X。

R122 发现相门控修复时序后 PAA 幅度过冲（批 22 amp_ratio 4.5×）。
根因分析：m_PAA 维护消耗项原代码用 y[3]=P（青霉素），但 MATLAB 原文用 X（生物量）。
m_PAA=1.05 g/g/h 是每克生物量消耗的 PAA 维护系数 → 应正比于 X 而非 P。

测试组合（批 22/23/36/60）：
  A: mode 0 + maintenance=P（基线，黄金回归）
  B: mode 1 + maintenance=P（R122 门控，幅度过冲）
  C: mode 1 + maintenance=X（R123 修复：门控 + 维护消耗对齐 MATLAB）
  D: mode 2 + maintenance=X（R123 修复：全门控 + 维护消耗对齐）

评估指标：
  - peak_lag_h: 引擎 vs 化验 PAA 峰值时刻差
  - paa_corr: 引擎 vs 化验 PAA 相关系数
  - amplitude_ratio: 引擎 PAA 峰值 / 化验 PAA 峰值
  - total_paa_error: 引擎 PAA 均值相对误差
"""
import io
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))

import numpy as np
import pandas as pd

from simulate import simulate_open_loop, load_batch
from calibration import calib_params

BATCHES = [22, 23, 36, 60]
CONFIGS = [
    ("A_baseline", 0, 0.0, 0),
    ("B_gate_P",   1, 0.0, 0),
    ("C_gate_X",   1, 0.0, 1),
    ("D_gate2_X",  2, 0.0, 1),
]


def extract_paa_metrics(sim, d):
    """提取 PAA 峰值时序和幅值指标。"""
    paa_lab = pd.to_numeric(d["PAA_offline"], errors="coerce")
    t_lab = d["time_h"]
    t_sim = sim["time_h"].to_numpy(float)

    t_aligned = [float(t_lab.iloc[i]) - 4.0 for i in range(len(d))]
    paa_sim_at = np.interp(t_aligned, t_sim, sim["PAA"].to_numpy(float))

    mask = (t_lab > 20) & paa_lab.notna() & (paa_lab != 0)
    t_points = [float(t_lab.iloc[i]) for i in range(len(d)) if mask.iloc[i]]
    sim_points = [paa_sim_at[i] for i in range(len(d)) if mask.iloc[i]]
    lab_points = [float(paa_lab.iloc[i]) for i in range(len(d)) if mask.iloc[i]]

    if len(t_points) < 2:
        return None

    sim_peak_idx = int(np.argmax(sim_points))
    lab_peak_idx = int(np.argmax(lab_points))

    corr = float(np.corrcoef(sim_points, lab_points)[0, 1]) if len(sim_points) > 1 else float("nan")
    amp_ratio = sim_points[sim_peak_idx] / lab_points[lab_peak_idx] if lab_points[lab_peak_idx] > 0 else float("nan")
    total_err = (np.mean(sim_points) / np.mean(lab_points) - 1.0) if np.mean(lab_points) > 0 else float("nan")

    return {
        "paa_corr": round(corr, 3),
        "peak_lag_h": round(t_points[sim_peak_idx] - t_points[lab_peak_idx], 1),
        "sim_peak_val": round(sim_points[sim_peak_idx], 1),
        "lab_peak_val": round(lab_points[lab_peak_idx], 1),
        "amplitude_ratio": round(amp_ratio, 3),
        "total_paa_error": round(total_err, 3),
        "sim_mean_paa": round(float(np.mean(sim_points)), 1),
        "lab_mean_paa": round(float(np.mean(lab_points)), 1),
    }


def main():
    results = {}
    for b in BATCHES:
        d = load_batch(b)
        base_params = calib_params(b)
        results[str(b)] = {"mu_p": round(base_params.get("mup", float("nan")), 4)}

        for name, mode, floor, maint in CONFIGS:
            params = dict(base_params)
            params["paa_gate_mode"] = mode
            params["paa_gate_floor"] = floor
            params["paa_maintenance_target"] = maint
            sim, _ = simulate_open_loop(b, params=params)
            sim = sim.copy()

            metrics = extract_paa_metrics(sim, d)
            if metrics:
                results[str(b)][name] = metrics

    # 汇总对比表
    print("\n" + "=" * 110)
    print("R123 D9(b) PAA 维护消耗修复探查 — m_PAA 目标变量 P→total_X")
    print("=" * 110)
    for b_str, r in results.items():
        print(f"\n--- 批 {b_str} (μp={r['mu_p']}) ---")
        print(f"{'config':<14} {'corr':>7} {'lag_h':>7} {'amp_ratio':>9} {'tot_err':>8} {'sim_peak':>9} {'lab_peak':>9}")
        for name, _, _, _ in CONFIGS:
            if name in r:
                m = r[name]
                print(f"{name:<14} {m['paa_corr']:>7.3f} {m['peak_lag_h']:>7.1f} "
                      f"{m['amplitude_ratio']:>9.3f} {m['total_paa_error']:>8.3f} "
                      f"{m['sim_peak_val']:>9.1f} {m['lab_peak_val']:>9.1f}")

    # 改善汇总
    print("\n" + "=" * 110)
    print("改善汇总（C/D vs B 对比：维护消耗修复后幅度变化）")
    print("=" * 110)
    for b_str, r in results.items():
        if "B_gate_P" not in r:
            continue
        b_amp = r["B_gate_P"]["amplitude_ratio"]
        b_corr = r["B_gate_P"]["paa_corr"]
        print(f"\n批 {b_str}: B(gate+P) amp={b_amp} corr={b_corr}")
        for name in ["C_gate_X", "D_gate2_X"]:
            if name in r:
                m = r[name]
                d_amp = m["amplitude_ratio"] - b_amp
                d_corr = m["paa_corr"] - b_corr
                print(f"  {name:<14}: Δamp={d_amp:+.3f} Δcorr={d_corr:+.3f} "
                      f"amp={m['amplitude_ratio']} corr={m['paa_corr']}")

    out = {
        "title": "R123 D9(b) PAA maintenance fix probe",
        "batches": results,
        "configs": {
            "A_baseline": "mode 0 + maintenance=P（黄金回归基线）",
            "B_gate_P": "mode 1 + maintenance=P（R122 门控，幅度过冲）",
            "C_gate_X": "mode 1 + maintenance=X（R123 修复：门控 + 维护消耗对齐 MATLAB）",
            "D_gate2_X": "mode 2 + maintenance=X（R123 修复：全门控 + 维护消耗对齐）",
        },
        "fix": "m_PAA 维护消耗目标 y[3]=P → total_X（对齐 MATLAB indpensim_ode.m）",
    }
    dst = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "runs", "p3", "paa_maintenance_fix_probe.json")
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\nSaved: {dst}", flush=True)


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""R122: D9(b) PAA 相门控探查——R121 根因修复验证。

对批 22/23/36/60 分别运行三种门控模式：
  mode 0: 不门控（基线，黄金回归守护）
  mode 1: 仅门控 X_1 项（Y_PAA_X * X_1 * f_paa）
  mode 2: 门控 X_1 + dP_dt 项（Y_PAA_P * dP_dt * f_paa + Y_PAA_X * X_1 * f_paa）

门控函数 f_paa = mean_P / (mean_P + s)（Michaelis-Menten 型）：
  s→∞（营养期）→ f_paa→0：抑制 PAA 消耗
  s→0 （生产期）→ f_paa→1：允许 PAA 消耗

评估指标：
  - peak_lag_h: 引擎 PAA 峰值时刻 vs 化验峰值时刻（负值=引擎偏早）
  - paa_corr: 引擎 vs 化验 PAA 相关系数
  - amplitude_ratio: 引擎 PAA 峰值 / 化验 PAA 峰值
  - total_paa_error: 引擎 PAA 均值 vs 化验 PAA 均值的相对误差

期望：mode 1/2 在高 μp 批（22/23）改善 peak_lag_h 和 paa_corr，
低 μp 批（36/60）保持零回归。
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
MODES = [0, 1, 2]
MODE_NAMES = {0: "off", 1: "gate_X1", 2: "gate_X1_dPdt"}


def extract_paa_metrics(sim, d):
    """提取 PAA 峰值时序和幅值指标。"""
    paa_lab = pd.to_numeric(d["PAA_offline"], errors="coerce")
    t_lab = d["time_h"]
    t_sim = sim["time_h"].to_numpy(float)

    # 引擎 PAA 在化验时点（4h 滞后）
    t_aligned = [float(t_lab.iloc[i]) - 4.0 for i in range(len(d))]
    paa_sim_at = np.interp(t_aligned, t_sim, sim["PAA"].to_numpy(float))

    # 有效锚点（t>20h, 非 NaN, 非零）
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
        "sim_peak_t": round(t_points[sim_peak_idx], 1),
        "lab_peak_t": round(t_points[lab_peak_idx], 1),
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

        for mode in MODES:
            params = dict(base_params)
            params["paa_gate_mode"] = mode
            sim, _ = simulate_open_loop(b, params=params)
            sim = sim.copy()

            metrics = extract_paa_metrics(sim, d)
            if metrics:
                results[str(b)][MODE_NAMES[mode]] = metrics

    # 汇总对比表
    print("\n" + "=" * 80)
    print("R122 D9(b) PAA 相门控探查 — 三模式对比")
    print("=" * 80)
    for b_str, r in results.items():
        print(f"\n--- 批 {b_str} (μp={r['mu_p']}) ---")
        print(f"{'模式':<12} {'corr':>7} {'lag_h':>7} {'amp_ratio':>9} {'tot_err':>8} {'sim_peak':>9} {'lab_peak':>9}")
        for mode_name in MODE_NAMES.values():
            if mode_name in r:
                m = r[mode_name]
                print(f"{mode_name:<12} {m['paa_corr']:>7.3f} {m['peak_lag_h']:>7.1f} "
                      f"{m['amplitude_ratio']:>9.3f} {m['total_paa_error']:>8.3f} "
                      f"{m['sim_peak_val']:>9.1f} {m['lab_peak_val']:>9.1f}")

    # 改善汇总
    print("\n" + "=" * 80)
    print("改善汇总（mode 1/2 vs mode 0 基线）")
    print("=" * 80)
    for b_str, r in results.items():
        if "off" not in r:
            continue
        base_corr = r["off"]["paa_corr"]
        base_lag = r["off"]["peak_lag_h"]
        print(f"\n批 {b_str}: 基线 corr={base_corr} lag={base_lag}h")
        for mode_name in ["gate_X1", "gate_X1_dPdt"]:
            if mode_name in r:
                m = r[mode_name]
                d_corr = m["paa_corr"] - base_corr
                d_lag = m["peak_lag_h"] - base_lag
                d_amp = m["amplitude_ratio"] - r["off"]["amplitude_ratio"]
                print(f"  {mode_name:<14}: Δcorr={d_corr:+.3f} Δlag={d_lag:+.1f}h Δamp={d_amp:+.3f}")

    out = {
        "title": "R122 D9(b) PAA phase-gating probe",
        "batches": results,
        "gate_function": "f_paa = mean_P / (mean_P + s)  [Michaelis-Menten]",
        "modes": {
            "0_off": "不门控（基线）",
            "1_gate_X1": "门控 Y_PAA_X * X_1 项",
            "2_gate_X1_dPdt": "门控 Y_PAA_X * X_1 + Y_PAA_P * dP_dt 项",
        },
        "expected": "高 μp 批(22/23) 改善 peak_lag_h 和 paa_corr；低 μp 批(36/60) 保持零回归",
    }
    dst = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "runs", "p3", "paa_gate_probe.json")
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\nSaved: {dst}", flush=True)


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""R123c: D9(b) PAA 一阶降解项扫描——控制门控幅度过冲。

R123b 发现：m_PAA 扫描无法修复批 22 幅度过冲（4.4x 结构性）。
根因：门控抑制 Y_PAA_X*X_1 消耗后，喂食项 Fpaa*PAA_c/V 持续累积 PAA，
m_PAA*X 维护消耗不足以抵消喂食累积。

R123c 方案：添加一阶 PAA 降解项 -paa_degrad_rate * PAA，
模拟 PAA 在发酵液中的缓慢降解（氧化/水解），作为被动消耗补充。

扫描 paa_degrad_rate ∈ {0.001, 0.002, 0.005, 0.008, 0.010, 0.015, 0.020}
固定：mode 1 + maintenance=X + m_PAA=0.10

目标：批 22/23/36/60 幅度比→~1.0，时序保持 lag=0h。
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
DEGRAD_VALUES = [0.001, 0.002, 0.005, 0.008, 0.010, 0.015, 0.020]
M_PAA_FIXED = 0.10


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
        "amplitude_ratio": round(amp_ratio, 3),
        "total_paa_error": round(total_err, 3),
    }


def main():
    results = {}
    for b in BATCHES:
        d = load_batch(b)
        base_params = calib_params(b)
        results[str(b)] = {"mu_p": round(base_params.get("mup", float("nan")), 4)}

        for deg in DEGRAD_VALUES:
            params = dict(base_params)
            params["paa_gate_mode"] = 1
            params["paa_gate_floor"] = 0.0
            params["paa_maintenance_target"] = 1  # X
            params["m_paa"] = M_PAA_FIXED
            params["paa_degrad_rate"] = deg
            sim, _ = simulate_open_loop(b, params=params)
            sim = sim.copy()

            metrics = extract_paa_metrics(sim, d)
            if metrics:
                results[str(b)][f"deg{deg}"] = metrics

    # 汇总对比表
    print("\n" + "=" * 110)
    print(f"R123c D9(b) PAA 降解项扫描 — mode 1 + maintenance=X + m_PAA={M_PAA_FIXED}")
    print("=" * 110)
    for b_str, r in results.items():
        print(f"\n--- 批 {b_str} (μp={r['mu_p']}) ---")
        print(f"{'degrad':<8} {'corr':>7} {'lag_h':>7} {'amp_ratio':>9} {'tot_err':>8}")
        for deg in DEGRAD_VALUES:
            key = f"deg{deg}"
            if key in r:
                m = r[key]
                print(f"{deg:<8.3f} {m['paa_corr']:>7.3f} {m['peak_lag_h']:>7.1f} "
                      f"{m['amplitude_ratio']:>9.3f} {m['total_paa_error']:>8.3f}")

    # 最优 degrad 推荐
    print("\n" + "=" * 110)
    print("最优 paa_degrad_rate 推荐（评分 = corr - 0.3*|amp_ratio-1|）")
    print("=" * 110)
    for b_str in ["22", "23", "36", "60"]:
        if b_str not in results:
            continue
        r = results[b_str]
        best_d = None
        best_score = -999
        for deg in DEGRAD_VALUES:
            key = f"deg{deg}"
            if key not in r:
                continue
            m = r[key]
            score = m["paa_corr"] - 0.3 * abs(m["amplitude_ratio"] - 1.0)
            if score > best_score:
                best_score = score
                best_d = deg
        print(f"批 {b_str}: 最优 degrad={best_d} (score={best_score:.3f})")
        if best_d is not None:
            m = r[f"deg{best_d}"]
            print(f"  → corr={m['paa_corr']} lag={m['peak_lag_h']}h amp={m['amplitude_ratio']}")

    out = {
        "title": "R123c D9(b) PAA degradation sweep",
        "batches": results,
        "gate_mode": 1,
        "maintenance_target": "X (total_X)",
        "m_paa_fixed": M_PAA_FIXED,
        "degrad_values": DEGRAD_VALUES,
        "scoring": "corr - 0.3 * |amplitude_ratio - 1.0|",
    }
    dst = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "runs", "p3", "paa_degrad_sweep.json")
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\nSaved: {dst}", flush=True)


if __name__ == "__main__":
    main()

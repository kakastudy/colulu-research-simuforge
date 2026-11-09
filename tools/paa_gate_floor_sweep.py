# -*- coding: utf-8 -*-
"""R122b: D9(b) PAA 相门控 floor 扫描——寻找最优门控下限。

对批 22/23/36/60 扫描 paa_gate_floor ∈ {0.0, 0.05, 0.10, 0.15, 0.20, 0.30}，
模式固定为 mode 1（仅门控 X_1 项）。

目标：在高 μp 批（22/23）保持时序改善（lag→0, corr→正），
同时控制幅度过冲（amp_ratio 接近 1.0）。
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
FLOORS = [0.0, 0.05, 0.10, 0.15, 0.20, 0.30]
GATE_MODE = 1  # gate X_1 only


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
    }


def main():
    results = {}
    for b in BATCHES:
        d = load_batch(b)
        base_params = calib_params(b)
        results[str(b)] = {"mu_p": round(base_params.get("mup", float("nan")), 4)}

        for floor in FLOORS:
            params = dict(base_params)
            params["paa_gate_mode"] = GATE_MODE
            params["paa_gate_floor"] = floor
            sim, _ = simulate_open_loop(b, params=params)
            sim = sim.copy()

            metrics = extract_paa_metrics(sim, d)
            if metrics:
                results[str(b)][f"floor_{floor}"] = metrics

    # 汇总对比表
    print("\n" + "=" * 100)
    print("R122b D9(b) PAA 相门控 floor 扫描 — mode 1 (gate X_1 only)")
    print("=" * 100)
    for b_str, r in results.items():
        print(f"\n--- 批 {b_str} (μp={r['mu_p']}) ---")
        print(f"{'floor':<8} {'corr':>7} {'lag_h':>7} {'amp_ratio':>9} {'tot_err':>8} {'sim_peak':>9} {'lab_peak':>9}")
        for floor in FLOORS:
            key = f"floor_{floor}"
            if key in r:
                m = r[key]
                print(f"{floor:<8.2f} {m['paa_corr']:>7.3f} {m['peak_lag_h']:>7.1f} "
                      f"{m['amplitude_ratio']:>9.3f} {m['total_paa_error']:>8.3f} "
                      f"{m['sim_peak_val']:>9.1f} {m['lab_peak_val']:>9.1f}")

    # 最优 floor 推荐
    print("\n" + "=" * 100)
    print("最优 floor 推荐（高 μp 批 corr 最大化 + 幅度过冲最小化）")
    print("=" * 100)
    for b_str in ["22", "23"]:
        if b_str not in results:
            continue
        r = results[b_str]
        best_floor = None
        best_score = -999
        for floor in FLOORS:
            key = f"floor_{floor}"
            if key not in r:
                continue
            m = r[key]
            # 评分：corr 越高越好，amp_ratio 越接近 1 越好
            score = m["paa_corr"] - 0.5 * abs(m["amplitude_ratio"] - 1.0)
            if score > best_score:
                best_score = score
                best_floor = floor
        print(f"批 {b_str}: 最优 floor={best_floor} (score={best_score:.3f})")

    out = {
        "title": "R122b D9(b) PAA gate floor sweep",
        "batches": results,
        "gate_mode": GATE_MODE,
        "floors": FLOORS,
        "scoring": "corr - 0.5 * |amplitude_ratio - 1.0|",
    }
    dst = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "runs", "p3", "paa_gate_floor_sweep.json")
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\nSaved: {dst}", flush=True)


if __name__ == "__main__":
    main()

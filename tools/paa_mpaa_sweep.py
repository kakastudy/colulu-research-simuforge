# -*- coding: utf-8 -*-
"""R123b: D9(b) PAA m_PAA 参数扫描——寻找门控+维护消耗的最优 m_PAA。

R123 发现：
  maintenance=P + gate: 时序修复但幅度过冲（4.5x）
  maintenance=X + gate: 幅度修复但时序崩溃（PAA 被过早消耗）

根因：m_PAA=1.05 是为 m_PAA*P 形式校准的。切换到 m_PAA*X 后，
因 X>>P（~5-10x），有效消耗率暴增。需重新校准 m_PAA。

扫描 m_PAA ∈ {0.05, 0.08, 0.10, 0.12, 0.15, 0.20, 0.25, 0.30}
固定模式：mode 1（gate X_1）+ maintenance=X（对齐 MATLAB）

目标：找到使高 μp 批（22/23）corr→正、lag→0、amp→~1.0 的 m_PAA 值。
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
M_PAA_VALUES = [0.05, 0.08, 0.10, 0.12, 0.15, 0.20, 0.25, 0.30]


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

        for m_paa in M_PAA_VALUES:
            params = dict(base_params)
            params["paa_gate_mode"] = 1
            params["paa_gate_floor"] = 0.0
            params["paa_maintenance_target"] = 1  # X
            params["m_paa"] = m_paa
            sim, _ = simulate_open_loop(b, params=params)
            sim = sim.copy()

            metrics = extract_paa_metrics(sim, d)
            if metrics:
                results[str(b)][f"m{m_paa}"] = metrics

    # 汇总对比表
    print("\n" + "=" * 110)
    print("R123b D9(b) PAA m_PAA 扫描 — mode 1 + maintenance=X")
    print("=" * 110)
    for b_str, r in results.items():
        print(f"\n--- 批 {b_str} (μp={r['mu_p']}) ---")
        print(f"{'m_PAA':<8} {'corr':>7} {'lag_h':>7} {'amp_ratio':>9} {'tot_err':>8}")
        for m_paa in M_PAA_VALUES:
            key = f"m{m_paa}"
            if key in r:
                m = r[key]
                print(f"{m_paa:<8.2f} {m['paa_corr']:>7.3f} {m['peak_lag_h']:>7.1f} "
                      f"{m['amplitude_ratio']:>9.3f} {m['total_paa_error']:>8.3f}")

    # 最优 m_PAA 推荐
    print("\n" + "=" * 110)
    print("最优 m_PAA 推荐（评分 = corr - 0.3*|amp_ratio-1|）")
    print("=" * 110)
    for b_str in ["22", "23"]:
        if b_str not in results:
            continue
        r = results[b_str]
        best_m = None
        best_score = -999
        for m_paa in M_PAA_VALUES:
            key = f"m{m_paa}"
            if key not in r:
                continue
            m = r[key]
            score = m["paa_corr"] - 0.3 * abs(m["amplitude_ratio"] - 1.0)
            if score > best_score:
                best_score = score
                best_m = m_paa
        print(f"批 {b_str}: 最优 m_PAA={best_m} (score={best_score:.3f})")
        if best_m is not None:
            m = r[f"m{best_m}"]
            print(f"  → corr={m['paa_corr']} lag={m['peak_lag_h']}h amp={m['amplitude_ratio']}")

    out = {
        "title": "R123b D9(b) PAA m_PAA sweep",
        "batches": results,
        "gate_mode": 1,
        "maintenance_target": "X (total_X)",
        "m_paa_values": M_PAA_VALUES,
        "scoring": "corr - 0.3 * |amplitude_ratio - 1.0|",
    }
    dst = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "runs", "p3", "paa_mpaa_sweep.json")
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\nSaved: {dst}", flush=True)


if __name__ == "__main__":
    main()

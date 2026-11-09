# -*- coding: utf-8 -*-
"""R124: D9(b) PAA 反相门控降解探查——修复 R123c 时序崩溃。

R123c 发现：恒定降解（degrad=0.005）修复幅度但时序崩溃（lag=-144h）。
根因：恒定降解在生产相也消耗 PAA → 峰值提前。

R124 方案：反相门控降解——降解仅在门控关闭时（生长相）激活。
  degrad = rate * PAA * (1 - f_paa)
  生长相 f_paa≈floor → (1-f_paa)≈1-floor（降解全速）
  生产相 f_paa≈1.0 → (1-f_paa)≈0（降解关闭）

物理依据：PAA 的溢出代谢（overflow metabolism）在生长相活跃——
青霉素合成途径未启动时，PAA 通过替代酶系被代谢消耗。

扫描 degrad ∈ {0.005, 0.008, 0.010, 0.015, 0.020, 0.025, 0.030}
固定：mode 1 + maintenance=X + m_PAA=0.10 + inverse_gate=True
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
DEGRAD_VALUES = [0.005, 0.008, 0.010, 0.015, 0.020, 0.025, 0.030]
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
            params["paa_degrad_inverse_gate"] = True
            sim, _ = simulate_open_loop(b, params=params)
            sim = sim.copy()

            metrics = extract_paa_metrics(sim, d)
            if metrics:
                results[str(b)][f"deg{deg}"] = metrics

    # 汇总对比表
    print("\n" + "=" * 110)
    print(f"R124 D9(b) PAA 反相门控降解扫描 — mode 1 + maintenance=X + m_PAA={M_PAA_FIXED}")
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
        "title": "R124 D9(b) PAA inverse-gated degradation sweep",
        "batches": results,
        "gate_mode": 1,
        "maintenance_target": "X (total_X)",
        "m_paa_fixed": M_PAA_FIXED,
        "inverse_gate": True,
        "degrad_values": DEGRAD_VALUES,
        "scoring": "corr - 0.3 * |amplitude_ratio - 1.0|",
        "fix": "degrad = rate * PAA * (1 - f_paa)——仅门控关闭时激活",
    }
    dst = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "runs", "p3", "paa_inverse_degrad_sweep.json")
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\nSaved: {dst}", flush=True)


if __name__ == "__main__":
    main()

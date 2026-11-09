# -*- coding: utf-8 -*-
"""R127: D4 故障注入算子探针——批 91 氧限制 + 批 92 pH 扰动。

D4 故障注入算子实现（model.py + simulate.py）：
  fault_type: 0=none, 1=oxygen_limit(降KLa), 2=ph_perturb(注酸), 3=feed_reduce(减喂食)
  fault_start/end: 故障时间窗
  fault_magnitude: 故障强度

探针目标：找到使引擎轨迹匹配化验轨迹的最优故障参数。
  批 91: 氧限制（S max=115, P max=8, DO2 min=10.4）
  批 92: pH 扰动（pH min=5.48, S max=45.8, P max=25.3）

评估指标：S/DO2/pH/P 通道 RMSE（对齐化验口径）+ yield_err。
"""
import io
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))

import numpy as np
import pandas as pd

from simulate import simulate_open_loop, load_batch, yield_metrics, classify_crash
from calibration import calib_params


def compute_rmse(sim, v3, channel, t_start=20, t_end=260):
    """计算指定通道的 RMSE（对齐化验口径，滞后 4h）。"""
    lab = pd.to_numeric(v3[channel], errors="coerce")
    t_lab = v3["time_h"]
    t_sim = sim["time_h"].to_numpy(float)

    t_aligned = [float(t_lab.iloc[i]) - 4.0 for i in range(len(v3))]
    sim_vals = np.interp(t_aligned, t_sim, sim[channel].to_numpy(float))

    mask = (t_lab > t_start) & (t_lab < t_end) & lab.notna()
    if mask.sum() < 2:
        return float("nan")
    sim_pts = sim_vals[mask]
    lab_pts = lab[mask].to_numpy(float)
    err = sim_pts - lab_pts
    return float(np.sqrt(np.mean(err**2)))


def main():
    results = {}

    # === 批 91: 氧限制故障扫描 ===
    print("=" * 80, flush=True)
    print("D4 故障注入探针 — 批 91 (氧限制)", flush=True)
    print("=" * 80, flush=True)

    b = 91
    d = load_batch(b)
    base_params = calib_params(b)

    # Baseline (no fault)
    sim_base, _ = simulate_open_loop(b, params=dict(base_params))
    sim_base = sim_base.copy()
    ym_base = yield_metrics(sim_base, d)
    err_base = ym_base["rel_err_total"]
    rmse_s = compute_rmse(sim_base, d, "S")
    rmse_do2 = compute_rmse(sim_base, d, "DO2")
    rmse_p = compute_rmse(sim_base, d, "P")
    print(f"Baseline (no fault): yield_err={err_base:.3f} RMSE_S={rmse_s:.1f} RMSE_DO2={rmse_do2:.1f} RMSE_P={rmse_p:.1f}", flush=True)
    results["91_baseline"] = {"yield_err": round(err_base, 4), "rmse_S": round(rmse_s, 2), "rmse_DO2": round(rmse_do2, 2), "rmse_P": round(rmse_p, 2)}

    # Sweep oxygen limitation
    best_91 = None
    best_score_91 = 1e9
    for fs in [0, 20, 40, 60, 80]:
        for fe in [240, 260]:
            for mag in [0.3, 0.5, 0.7, 0.9]:
                params = dict(base_params)
                params["fault_type"] = 1
                params["fault_start"] = fs
                params["fault_end"] = fe
                params["fault_magnitude"] = mag
                try:
                    sim, _ = simulate_open_loop(b, params=params)
                    sim = sim.copy()
                    ym = yield_metrics(sim, d)
                    err = ym["rel_err_total"]
                    rmse_s = compute_rmse(sim, d, "S")
                    rmse_do2 = compute_rmse(sim, d, "DO2")
                    rmse_p = compute_rmse(sim, d, "P")
                    score = err + 0.1 * rmse_s / 100 + 0.1 * rmse_do2 / 100
                    if score < best_score_91:
                        best_score_91 = score
                        best_91 = {"fault_start": fs, "fault_end": fe, "fault_magnitude": mag,
                                   "yield_err": round(err, 4), "rmse_S": round(rmse_s, 2),
                                   "rmse_DO2": round(rmse_do2, 2), "rmse_P": round(rmse_p, 2)}
                    results[f"91_oxy_fs{fs}_fe{fe}_mag{mag}"] = {
                        "yield_err": round(err, 4), "rmse_S": round(rmse_s, 2),
                        "rmse_DO2": round(rmse_do2, 2), "rmse_P": round(rmse_p, 2)}
                except Exception as e:
                    pass

    if best_91:
        print(f"\nBest 91: {best_91}", flush=True)
        results["91_best"] = best_91

    # === 批 92: pH 扰动故障扫描 ===
    print("\n" + "=" * 80, flush=True)
    print("D4 故障注入探针 — 批 92 (pH 扰动)", flush=True)
    print("=" * 80, flush=True)

    b = 92
    d = load_batch(b)
    base_params = calib_params(b)

    # Baseline (no fault)
    sim_base, _ = simulate_open_loop(b, params=dict(base_params))
    sim_base = sim_base.copy()
    ym_base = yield_metrics(sim_base, d)
    err_base = ym_base["rel_err_total"]
    rmse_ph = compute_rmse(sim_base, d, "pH")
    rmse_s = compute_rmse(sim_base, d, "S")
    rmse_p = compute_rmse(sim_base, d, "P")
    print(f"Baseline (no fault): yield_err={err_base:.3f} RMSE_pH={rmse_ph:.2f} RMSE_S={rmse_s:.1f} RMSE_P={rmse_p:.1f}", flush=True)
    results["92_baseline"] = {"yield_err": round(err_base, 4), "rmse_pH": round(rmse_ph, 2), "rmse_S": round(rmse_s, 2), "rmse_P": round(rmse_p, 2)}

    # Sweep pH perturbation
    best_92 = None
    best_score_92 = 1e9
    for fs in [40, 60, 80, 100]:
        for fe_offset in [40, 80]:
            fe = fs + fe_offset
            for mag in [100, 200, 500, 1000]:
                params = dict(base_params)
                params["fault_type"] = 2
                params["fault_start"] = fs
                params["fault_end"] = fe
                params["fault_magnitude"] = mag
                try:
                    sim, _ = simulate_open_loop(b, params=params)
                    sim = sim.copy()
                    ym = yield_metrics(sim, d)
                    err = ym["rel_err_total"]
                    rmse_ph = compute_rmse(sim, d, "pH")
                    rmse_s = compute_rmse(sim, d, "S")
                    rmse_p = compute_rmse(sim, d, "P")
                    score = err + 0.1 * rmse_ph / 1 + 0.1 * rmse_s / 100
                    if score < best_score_92:
                        best_score_92 = score
                        best_92 = {"fault_start": fs, "fault_end": fe, "fault_magnitude": mag,
                                   "yield_err": round(err, 4), "rmse_pH": round(rmse_ph, 2),
                                   "rmse_S": round(rmse_s, 2), "rmse_P": round(rmse_p, 2)}
                    results[f"92_ph_fs{fs}_fe{fe}_mag{mag}"] = {
                        "yield_err": round(err, 4), "rmse_pH": round(rmse_ph, 2),
                        "rmse_S": round(rmse_s, 2), "rmse_P": round(rmse_p, 2)}
                except Exception as e:
                    pass

    if best_92:
        print(f"\nBest 92: {best_92}", flush=True)
        results["92_best"] = best_92

    # Save
    dst = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "runs", "p3", "d4_fault_injection_probe.json")
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\nSaved: {dst}", flush=True)


if __name__ == "__main__":
    main()

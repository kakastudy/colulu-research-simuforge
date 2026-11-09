# -*- coding: utf-8 -*-
"""R129: ODE 级生物量衰亡项校准——批 91 底物累积修复。

R127 D4 探针发现：批 91 底物累积根因是生物量衰亡（DO2 恢复后 S 仍从 t=96h
线性累积至 115）。模型现有 r_d1/r_d4 是组分间迁移（总量守恒），无真正衰亡项。

R129 方案：在生物量 ODE 各组分加 -kd·y[comp] 项（biomass_death_rate 参数），
减少总生物量 → 底物消耗减少 → 喂食持续 → S 累积。默认 kd=0（黄金回归零回归）。

扫描 kd ∈ {0, 0.001, 0.002, 0.003, 0.005, 0.008, 0.010, 0.015, 0.020}
评估：S/DO2/P 通道 RMSE + yield_err
"""
import io
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))

import numpy as np
import pandas as pd

from simulate import simulate_open_loop, load_batch, yield_metrics
from calibration import calib_params


def compute_rmse(sim, v3, channel, t_start=20, t_end=260):
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
    return float(np.sqrt(np.mean((sim_pts - lab_pts) ** 2)))


def main():
    b = 91
    d = load_batch(b)
    base_params = calib_params(b)

    # Baseline (no death)
    sim_base, _ = simulate_open_loop(b, params=dict(base_params))
    sim_base = sim_base.copy()
    ym_base = yield_metrics(sim_base, d)
    print("Baseline (kd=0): yield_err=%.4f RMSE_S=%.1f RMSE_DO2=%.1f RMSE_P=%.1f" % (
        ym_base["rel_err_total"],
        compute_rmse(sim_base, d, "S"),
        compute_rmse(sim_base, d, "DO2"),
        compute_rmse(sim_base, d, "P")), flush=True)

    print()
    print("Biomass death rate sweep:")
    print("%10s %10s %8s %8s %8s %8s" % ("kd", "yield_err", "RMSE_S", "RMSE_DO2", "RMSE_P", "S_max"))

    results = {}
    for kd in [0.0, 0.001, 0.002, 0.003, 0.005, 0.008, 0.010, 0.015, 0.020]:
        params = dict(base_params)
        params["biomass_death_rate"] = kd
        sim, _ = simulate_open_loop(b, params=params)
        sim = sim.copy()
        ym = yield_metrics(sim, d)
        err = ym["rel_err_total"]
        rmse_s = compute_rmse(sim, d, "S")
        rmse_do2 = compute_rmse(sim, d, "DO2")
        rmse_p = compute_rmse(sim, d, "P")
        s_max = float(sim["S"].max())
        print("%10.4f %10.4f %8.1f %8.1f %8.1f %8.1f" % (kd, err, rmse_s, rmse_do2, rmse_p, s_max), flush=True)
        results[f"kd{kd}"] = {
            "yield_err": round(err, 4), "rmse_S": round(rmse_s, 2),
            "rmse_DO2": round(rmse_do2, 2), "rmse_P": round(rmse_p, 2),
            "S_max": round(s_max, 1)}

    # Find best trade-off: minimize S RMSE while keeping yield reasonable
    best_key = None
    best_score = 1e9
    for key, r in results.items():
        # Score: S RMSE most important, yield secondary
        score = r["rmse_S"] * 0.5 + abs(r["yield_err"]) * 0.3 + r["rmse_DO2"] * 0.2
        if score < best_score:
            best_score = score
            best_key = key
    print()
    print("Best trade-off: %s (score=%.2f)" % (best_key, best_score))
    print("  → yield_err=%.4f RMSE_S=%.1f RMSE_DO2=%.1f RMSE_P=%.1f S_max=%.1f" % (
        results[best_key]["yield_err"], results[best_key]["rmse_S"],
        results[best_key]["rmse_DO2"], results[best_key]["rmse_P"],
        results[best_key]["S_max"]))

    dst = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "runs", "p3", "d9_death_term_batch91.json")
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("\nSaved: %s" % dst, flush=True)


if __name__ == "__main__":
    main()

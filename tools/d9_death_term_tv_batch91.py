# -*- coding: utf-8 -*-
"""R129b: ODE 级生物量衰亡项 time-varying 校准——批 91。

R129 发现：常数 kd=0.005 给出 S_max=112.7（lab=115.3）但 P_max=8.1（lab=8.4）。
常数衰亡从 t=0 开始，过早降低 P 产率。time-varying 衰亡（t>=death_start 激活）
保留早期产 P 同时实现后期 S 累积。

扫描 death_start ∈ {0, 60, 80, 90, 96, 100, 120, 140} × kd ∈ {0.003, 0.005, 0.008}
评估：S/P 通道 RMSE + yield_err + S_max + P_max
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

    # Baseline
    sim_base, _ = simulate_open_loop(b, params=dict(base_params))
    sim_base = sim_base.copy()
    ym_base = yield_metrics(sim_base, d)
    print("Baseline (kd=0): yield_err=%.4f S_max=%.1f P_max=%.1f RMSE_S=%.1f RMSE_P=%.1f" % (
        ym_base["rel_err_total"], sim_base["S"].max(), sim_base["P"].max(),
        compute_rmse(sim_base, d, "S"), compute_rmse(sim_base, d, "P")), flush=True)

    print()
    print("Time-varying death sweep (death_start × kd):")
    print("%12s %8s %10s %8s %8s %8s %8s" % ("death_start", "kd", "yield_err", "S_max", "P_max", "RMSE_S", "RMSE_P"))

    results = {}
    for kd in [0.003, 0.005, 0.008]:
        for ds in [0, 60, 80, 90, 96, 100, 120, 140]:
            params = dict(base_params)
            params["biomass_death_rate"] = kd
            params["death_start"] = ds
            sim, _ = simulate_open_loop(b, params=params)
            sim = sim.copy()
            ym = yield_metrics(sim, d)
            err = ym["rel_err_total"]
            s_max = float(sim["S"].max())
            p_max = float(sim["P"].max())
            rmse_s = compute_rmse(sim, d, "S")
            rmse_p = compute_rmse(sim, d, "P")
            print("%12d %8.4f %10.4f %8.1f %8.1f %8.1f %8.1f" % (
                ds, kd, err, s_max, p_max, rmse_s, rmse_p), flush=True)
            results[f"ds{ds}_kd{kd}"] = {
                "yield_err": round(err, 4), "S_max": round(s_max, 1), "P_max": round(p_max, 1),
                "rmse_S": round(rmse_s, 2), "rmse_P": round(rmse_p, 2)}

    # Find best trade-off: minimize combined S+P RMSE while keeping yield reasonable
    best_key = None
    best_score = 1e9
    for key, r in results.items():
        score = r["rmse_S"] * 0.4 + r["rmse_P"] * 0.3 + abs(r["yield_err"]) * 0.3
        if score < best_score:
            best_score = score
            best_key = key
    print()
    print("Best trade-off: %s (score=%.2f)" % (best_key, best_score))
    print("  → yield_err=%.4f S_max=%.1f P_max=%.1f RMSE_S=%.1f RMSE_P=%.1f" % (
        results[best_key]["yield_err"], results[best_key]["S_max"],
        results[best_key]["P_max"], results[best_key]["rmse_S"],
        results[best_key]["rmse_P"]))

    dst = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "runs", "p3", "d9_death_term_tv_batch91.json")
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("\nSaved: %s" % dst, flush=True)


if __name__ == "__main__":
    main()

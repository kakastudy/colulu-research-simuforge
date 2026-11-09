# -*- coding: utf-8 -*-
"""R127b: D4 氧限制故障精细扫描——批 91 幅度甜点。

R127 发现：mag=0.7 捕获 S 累积好（RMSE_S 16.5→3.4）但过度降低 DO2/P。
mag=0.5 几乎无改善。需要在 0.5-0.7 之间找甜点。

扫描 mag ∈ {0.50, 0.55, 0.58, 0.60, 0.62, 0.65, 0.70}
固定 fault_start=0, fault_end=240
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
    print("Baseline: yield_err=%.4f RMSE_S=%.1f RMSE_DO2=%.1f RMSE_P=%.1f" % (
        ym_base["rel_err_total"],
        compute_rmse(sim_base, d, "S"),
        compute_rmse(sim_base, d, "DO2"),
        compute_rmse(sim_base, d, "P")), flush=True)

    print()
    print("Magnitude sweep (fault_type=1, fs=0, fe=240):")
    print("%8s %10s %8s %8s %8s" % ("mag", "yield_err", "RMSE_S", "RMSE_DO2", "RMSE_P"))

    results = {}
    for mag in [0.50, 0.55, 0.58, 0.60, 0.62, 0.65, 0.70]:
        params = dict(base_params)
        params["fault_type"] = 1
        params["fault_start"] = 0.0
        params["fault_end"] = 240.0
        params["fault_magnitude"] = mag
        sim, _ = simulate_open_loop(b, params=params)
        sim = sim.copy()
        ym = yield_metrics(sim, d)
        err = ym["rel_err_total"]
        rmse_s = compute_rmse(sim, d, "S")
        rmse_do2 = compute_rmse(sim, d, "DO2")
        rmse_p = compute_rmse(sim, d, "P")
        print("%8.2f %10.4f %8.1f %8.1f %8.1f" % (mag, err, rmse_s, rmse_do2, rmse_p), flush=True)
        results[f"mag{mag}"] = {
            "yield_err": round(err, 4), "rmse_S": round(rmse_s, 2),
            "rmse_DO2": round(rmse_do2, 2), "rmse_P": round(rmse_p, 2)}

    # Find best trade-off: minimize S RMSE while keeping DO2 RMSE reasonable
    best_key = None
    best_score = 1e9
    for key, r in results.items():
        # Score: S RMSE is most important (substrate accumulation), DO2/P secondary
        score = r["rmse_S"] * 0.5 + r["rmse_DO2"] * 0.3 + r["rmse_P"] * 0.2 + abs(r["yield_err"]) * 0.1
        if score < best_score:
            best_score = score
            best_key = key
    print()
    print("Best trade-off: %s (score=%.2f)" % (best_key, best_score))
    print("  → yield_err=%.4f RMSE_S=%.1f RMSE_DO2=%.1f RMSE_P=%.1f" % (
        results[best_key]["yield_err"], results[best_key]["rmse_S"],
        results[best_key]["rmse_DO2"], results[best_key]["rmse_P"]))

    dst = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "runs", "p3", "d4_oxy_fine_sweep.json")
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("\nSaved: %s" % dst, flush=True)


if __name__ == "__main__":
    main()

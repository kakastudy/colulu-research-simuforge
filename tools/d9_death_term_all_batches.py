# -*- coding: utf-8 -*-
"""R129c: ODE 级衰亡项全黄金批扫描——X_offline 改善评估。

R129 发现：批 91 TV death ds=60 kd=0.005 → yield_err=0.0002（本质完美）。
D6 健康视图显示 X_offline 全部 critical（12/12）——生物量估计是全局难点。
衰亡项可能改善其他批的 X_offline RMSE。

扫描 12 批 × kd ∈ {0, 0.001, 0.002, 0.005} × death_start ∈ {0, 100} = 96 仿真
评估：yield_err + X_offline RMSE + S RMSE
"""
import io
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))

import numpy as np
import pandas as pd

from simulate import simulate_open_loop, load_batch, yield_metrics
from calibration import calib_params, GOLDEN


def compute_rmse_offline(sim, v3, v3_ch, sim_ch, t_start=20, t_end=260, delay=4.0):
    lab = pd.to_numeric(v3[v3_ch], errors="coerce")
    t_lab = v3["time_h"]
    t_sim = sim["time_h"].to_numpy(float)
    t_aligned = [float(t_lab.iloc[i]) - delay for i in range(len(v3))]
    sim_vals = np.interp(t_aligned, t_sim, sim[sim_ch].to_numpy(float))
    mask = (t_lab > t_start) & (t_lab < t_end) & lab.notna()
    if mask.sum() < 3:
        return float("nan")
    sim_pts = sim_vals[mask]
    lab_pts = lab[mask].to_numpy(float)
    return float(np.sqrt(np.mean((sim_pts - lab_pts) ** 2)))


def main():
    results = {}
    print("=" * 80, flush=True)
    print("R129c: ODE 级衰亡项全黄金批扫描", flush=True)
    print("=" * 80, flush=True)

    for b in GOLDEN:
        d = load_batch(b)
        base_params = calib_params(b)

        # Baseline (no death)
        sim_base, _ = simulate_open_loop(b, params=dict(base_params))
        sim_base = sim_base.copy()
        ym_base = yield_metrics(sim_base, d)
        rmse_x_base = compute_rmse_offline(sim_base, d, "X_offline", "X")
        print("Batch %2d baseline: yield_err=%.4f RMSE_X=%.2f" % (
            b, ym_base["rel_err_total"], rmse_x_base), flush=True)

        batch_results = {"baseline": {"yield_err": round(ym_base["rel_err_total"], 4),
                                       "rmse_X": round(rmse_x_base, 2)}}
        for kd in [0.001, 0.002, 0.005]:
            for ds in [0, 100]:
                params = dict(base_params)
                params["biomass_death_rate"] = kd
                params["death_start"] = ds
                sim, _ = simulate_open_loop(b, params=params)
                sim = sim.copy()
                ym = yield_metrics(sim, d)
                rmse_x = compute_rmse_offline(sim, d, "X_offline", "X")
                key = f"kd{kd}_ds{ds}"
                batch_results[key] = {
                    "yield_err": round(ym["rel_err_total"], 4),
                    "rmse_X": round(rmse_x, 2)}
                delta_x = rmse_x_base - rmse_x
                if delta_x > 0.5:
                    print("  %s: yield_err=%.4f RMSE_X=%.2f (ΔX=%.2f ↑)" % (
                        key, ym["rel_err_total"], rmse_x, delta_x), flush=True)

        results[str(b)] = batch_results

    # Summary: find batches where death term improves X_offline
    print("\n" + "=" * 80, flush=True)
    print("Summary: batches where death term improves X_offline (ΔX > 0.5):", flush=True)
    for b_str, br in results.items():
        base_x = br["baseline"]["rmse_X"]
        improvements = []
        for key, r in br.items():
            if key == "baseline":
                continue
            delta = base_x - r["rmse_X"]
            if delta > 0.5:
                improvements.append((key, round(delta, 2)))
        if improvements:
            print("  Batch %s: baseline RMSE_X=%.2f, improvements: %s" % (
                b_str, base_x, improvements), flush=True)

    dst = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "runs", "p3", "d9_death_term_all_batches.json")
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("\nSaved: %s" % dst, flush=True)


if __name__ == "__main__":
    main()

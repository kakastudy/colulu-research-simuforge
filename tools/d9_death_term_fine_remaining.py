# -*- coding: utf-8 -*-
"""R129e: 衰亡项精细校准——未启用 6 批（23/27/36/55/60/92）。

R129d 扫描发现：批 23/27/36/55/60/92 在 kd∈{0.001,0.002,0.005} 下改善 X 但恶化 yield。
需要更精细的 kd（更小值）和更多 death_start 选项来找到 yield 可接受的平衡点。

扫描 6 批 × kd∈{0.0005, 0.001, 0.0015, 0.002, 0.003} × ds∈{0, 80, 120, 160, 200} = 150 仿真
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
from calibration import calib_params


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
    batches = [23, 27, 36, 55, 60, 92]
    results = {}
    print("=" * 90, flush=True)
    print("R129e: 衰亡项精细校准——未启用 6 批", flush=True)
    print("=" * 90, flush=True)

    for b in batches:
        d = load_batch(b)
        base_params = calib_params(b)

        # Baseline
        sim_base, _ = simulate_open_loop(b, params=dict(base_params))
        sim_base = sim_base.copy()
        ym_base = yield_metrics(sim_base, d)
        rmse_x_base = compute_rmse_offline(sim_base, d, "X_offline", "X")
        print("Batch %2d baseline: yield_err=%.4f RMSE_X=%.2f" % (
            b, ym_base["rel_err_total"], rmse_x_base), flush=True)

        batch_results = {"baseline": {"yield_err": round(ym_base["rel_err_total"], 4),
                                       "rmse_X": round(rmse_x_base, 2)}}
        for kd in [0.0005, 0.001, 0.0015, 0.002, 0.003]:
            for ds in [0, 80, 120, 160, 200]:
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
                # Show promising configs: X improves AND yield within ±5%
                if delta_x > 0.5 and abs(ym["rel_err_total"]) <= 0.05:
                    print("  %s: yield_err=%.4f RMSE_X=%.2f (ΔX=%.2f ↑, yield OK)" % (
                        key, ym["rel_err_total"], rmse_x, delta_x), flush=True)

        # Find best config: X improves > 1.0 AND yield within ±5%
        best_key = None
        best_score = -1
        for key, r in batch_results.items():
            if key == "baseline":
                continue
            delta_x = rmse_x_base - r["rmse_X"]
            ye = r["yield_err"]
            if delta_x > 1.0 and abs(ye) <= 0.05:
                score = delta_x
                if score > best_score:
                    best_score = score
                    best_key = key
        if best_key:
            r = batch_results[best_key]
            print("  BEST: %s → yield_err=%.4f RMSE_X=%.2f (ΔX=%.2f)" % (
                best_key, r["yield_err"], r["rmse_X"], best_score), flush=True)
        else:
            print("  NO acceptable config (X improves >1.0 AND yield within ±5%)", flush=True)

        results[str(b)] = batch_results
        print(flush=True)

    # Summary
    print("=" * 90, flush=True)
    print("Summary: batches with acceptable death-term configs:", flush=True)
    for b_str, br in results.items():
        base_x = br["baseline"]["rmse_X"]
        base_ye = br["baseline"]["yield_err"]
        best_key = None
        best_delta = 0
        for key, r in br.items():
            if key == "baseline":
                continue
            delta = base_x - r["rmse_X"]
            if delta > 1.0 and abs(r["yield_err"]) <= 0.05:
                if delta > best_delta:
                    best_delta = delta
                    best_key = key
        if best_key:
            r = br[best_key]
            print("  Batch %s: %s → yield %.4f→%.4f, RMSE_X %.2f→%.2f (Δ=%.2f)" % (
                b_str, best_key, base_ye, r["yield_err"], base_x, r["rmse_X"], best_delta), flush=True)
        else:
            print("  Batch %s: NO acceptable config" % b_str, flush=True)

    dst = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "runs", "p3", "d9_death_term_fine_remaining.json")
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("\nSaved: %s" % dst, flush=True)


if __name__ == "__main__":
    main()

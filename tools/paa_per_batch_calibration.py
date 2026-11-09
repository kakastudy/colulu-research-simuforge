# -*- coding: utf-8 -*-
"""R125: D9(b) PAA 逐批 m_PAA + degrad 校准——为 calib_params 提供最优值。

聚焦扫描：12 批 × m_PAA(5) × degrad(3) = 180 仿真。
m_PAA ∈ {0.10, 0.30, 0.50, 1.0, 2.0}
degrad ∈ {0.003, 0.0045, 0.008}
固定：mode 1 + maintenance=X + floor=0.0 + inverse_gate=True
"""
import io
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))

import numpy as np
import pandas as pd

from simulate import simulate_open_loop, load_batch
from calibration import calib_params, GOLDEN

M_PAA_VALUES = [0.10, 0.30, 0.50, 1.0, 2.0]
DEGRAD_VALUES = [0.003, 0.0045, 0.008]


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
    for b in GOLDEN:
        try:
            d = load_batch(b)
        except Exception as e:
            print(f"Batch {b}: load failed: {e}", flush=True)
            continue
        base_params = calib_params(b)
        results[str(b)] = {"mu_p": round(base_params.get("mup", float("nan")), 4)}

        best_key = None
        best_score = -999

        for m_paa in M_PAA_VALUES:
            for deg in DEGRAD_VALUES:
                params = dict(base_params)
                params["paa_gate_mode"] = 1
                params["paa_gate_floor"] = 0.0
                params["paa_maintenance_target"] = 1  # X
                params["m_paa"] = m_paa
                params["paa_degrad_rate"] = deg
                params["paa_degrad_inverse_gate"] = True
                sim, _ = simulate_open_loop(b, params=params)
                sim = sim.copy()

                metrics = extract_paa_metrics(sim, d)
                if metrics:
                    key = f"m{m_paa}_d{deg}"
                    results[str(b)][key] = metrics
                    score = metrics["paa_corr"] - 0.3 * abs(metrics["amplitude_ratio"] - 1.0) - 0.1 * abs(metrics["peak_lag_h"])
                    if score > best_score:
                        best_score = score
                        best_key = key

        if best_key:
            results[str(b)]["optimal"] = best_key
            results[str(b)]["optimal_score"] = round(best_score, 3)
            m = results[str(b)][best_key]
            print(f"Batch {b} (μp={results[str(b)]['mu_p']}): optimal {best_key} → "
                  f"corr={m['paa_corr']} lag={m['peak_lag_h']}h amp={m['amplitude_ratio']} (score={best_score:.3f})",
                  flush=True)

    # 汇总表
    print("\n" + "=" * 80, flush=True)
    print("R125 D9(b) PAA 逐批 m_PAA + degrad 校准结果", flush=True)
    print("=" * 80, flush=True)
    print(f"{'Batch':>6} {'μp':>8} {'Optimal m_PAA':>14} {'degrad':>8} {'corr':>7} {'lag_h':>7} {'amp':>7}", flush=True)
    for b_str, r in results.items():
        if "optimal" not in r:
            continue
        m_paa_str = r["optimal"].split("_")[0][1:]
        deg_str = r["optimal"].split("_")[1][1:]
        m = r[r["optimal"]]
        print(f"{b_str:>6} {r['mu_p']:>8.3f} {m_paa_str:>14} {deg_str:>8} "
              f"{m['paa_corr']:>7.3f} {m['peak_lag_h']:>7.1f} {m['amplitude_ratio']:>7.3f}",
              flush=True)

    # 导出 calib_params 可用的 JSON
    cal_out = {}
    for b_str, r in results.items():
        if "optimal" not in r:
            continue
        parts = r["optimal"].split("_")
        m_paa = float(parts[0][1:])
        deg = float(parts[1][1:])
        cal_out[str(b)] = {
            "m_paa": m_paa,
            "paa_degrad_rate": deg,
            "paa_gate_mode": 1,
            "paa_gate_floor": 0.0,
            "paa_maintenance_target": 1,
            "paa_degrad_inverse_gate": True,
            "score": r["optimal_score"],
        }

    dst = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "runs", "p3", "paa_per_batch_calibration.json")
    with open(dst, "w", encoding="utf-8") as f:
        json.dump({"calibration": cal_out, "raw_results": results}, f, ensure_ascii=False, indent=2)
    print(f"\nSaved: {dst}", flush=True)


if __name__ == "__main__":
    main()

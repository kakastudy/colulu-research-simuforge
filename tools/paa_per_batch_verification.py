# -*- coding: utf-8 -*-
"""R125 验证：PAA 逐批校准后的幅度改善。

对每个黄金批：
1. 用 calib_params（含逐批 m_paa + degrad）+ 门控模式（mode 1 + inv_gate）
2. 提取 PAA 指标（corr, lag, amp）
3. 对比 mode 0（基线）和 mode 1（门控+校准）
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

    return {
        "paa_corr": round(corr, 3),
        "peak_lag_h": round(t_points[sim_peak_idx] - t_points[lab_peak_idx], 1),
        "amplitude_ratio": round(amp_ratio, 3),
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

        # Mode 0 (baseline, no gate)
        params0 = dict(base_params)
        sim0, _ = simulate_open_loop(b, params=params0)
        sim0 = sim0.copy()
        m0 = extract_paa_metrics(sim0, d)

        # Mode 1 (gate + per-batch calibration)
        params1 = dict(base_params)
        params1["paa_gate_mode"] = 1
        params1["paa_gate_floor"] = 0.0
        params1["paa_maintenance_target"] = 1
        params1["paa_degrad_inverse_gate"] = True
        sim1, _ = simulate_open_loop(b, params=params1)
        sim1 = sim1.copy()
        m1 = extract_paa_metrics(sim1, d)

        results[str(b)] = {
            "mu_p": round(base_params.get("mup", float("nan")), 4),
            "m_paa": base_params.get("m_paa", None),
            "degrad": base_params.get("paa_degrad_rate", None),
            "mode0": m0,
            "mode1": m1,
        }

        m_paa = base_params.get("m_paa", "N/A")
        deg = base_params.get("paa_degrad_rate", "N/A")
        print(f"Batch {b} (μp={results[str(b)]['mu_p']}, m_paa={m_paa}, deg={deg}):", flush=True)
        if m0:
            print(f"  mode0: corr={m0['paa_corr']} lag={m0['peak_lag_h']}h amp={m0['amplitude_ratio']}", flush=True)
        if m1:
            print(f"  mode1: corr={m1['paa_corr']} lag={m1['peak_lag_h']}h amp={m1['amplitude_ratio']}", flush=True)

    # 汇总表
    print("\n" + "=" * 120, flush=True)
    print("R125 PAA 逐批校准验证汇总", flush=True)
    print("=" * 120, flush=True)
    print(f"{'Batch':>6} {'μp':>8} {'m_paa':>7} {'degrad':>8} | {'m0_corr':>8} {'m0_amp':>7} | {'m1_corr':>8} {'m1_amp':>7} {'m1_lag':>7}", flush=True)
    for b_str, r in results.items():
        m0 = r["mode0"]
        m1 = r["mode1"]
        m0_corr = f"{m0['paa_corr']:.3f}" if m0 else "N/A"
        m0_amp = f"{m0['amplitude_ratio']:.3f}" if m0 else "N/A"
        m1_corr = f"{m1['paa_corr']:.3f}" if m1 else "N/A"
        m1_amp = f"{m1['amplitude_ratio']:.3f}" if m1 else "N/A"
        m1_lag = f"{m1['peak_lag_h']:.1f}" if m1 else "N/A"
        print(f"{b_str:>6} {r['mu_p']:>8.3f} {r['m_paa']:>7} {r['degrad']:>8} | "
              f"{m0_corr:>8} {m0_amp:>7} | {m1_corr:>8} {m1_amp:>7} {m1_lag:>7}", flush=True)

    dst = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "runs", "p3", "paa_per_batch_verification.json")
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\nSaved: {dst}", flush=True)


if __name__ == "__main__":
    main()

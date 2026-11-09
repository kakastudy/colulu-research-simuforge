# -*- coding: utf-8 -*-
"""R121b: PAA 轨迹形状探查——反相关批(22/23) vs 近完美批(36/60)。

输出各批 PAA 在化验时点的引擎值 vs 化验值序列，识别反相关来源：
- 时序错位（引擎峰值早于/晚于化验峰值）
- 幅值偏差（系统性高估/低估）
- 形状失真（振荡/拐点位置不同）
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


def main():
    results = {}
    for b in BATCHES:
        d = load_batch(b)
        params = calib_params(b)
        sim, _ = simulate_open_loop(b, params)
        sim = sim.copy()

        paa_lab = pd.to_numeric(d["PAA_offline"], errors="coerce")
        t_lab = d["time_h"]
        t_sim = sim["time_h"].to_numpy(float)

        # 引擎 PAA 在化验时点（4h 滞后）
        t_aligned = [float(t_lab.iloc[i]) - 4.0 for i in range(len(d))]
        paa_sim_at = np.interp(t_aligned, t_sim, sim["PAA"].to_numpy(float))

        # 有效锚点
        mask = (t_lab > 20) & paa_lab.notna() & (paa_lab != 0)
        t_points = [float(t_lab.iloc[i]) for i in range(len(d)) if mask.iloc[i]]
        sim_points = [paa_sim_at[i] for i in range(len(d)) if mask.iloc[i]]
        lab_points = [float(paa_lab.iloc[i]) for i in range(len(d)) if mask.iloc[i]]

        # 峰值位置
        sim_peak_idx = int(np.argmax(sim_points))
        lab_peak_idx = int(np.argmax(lab_points))

        row = {
            "batch": b,
            "mu_p": round(float(params.get("mup", float("nan"))), 4),
            "paa_corr": round(float(np.corrcoef(sim_points, lab_points)[0, 1]), 3),
            "sim_peak_t": round(t_points[sim_peak_idx], 1),
            "lab_peak_t": round(t_points[lab_peak_idx], 1),
            "peak_lag_h": round(t_points[sim_peak_idx] - t_points[lab_peak_idx], 1),
            "sim_peak_val": round(sim_points[sim_peak_idx], 1),
            "lab_peak_val": round(lab_points[lab_peak_idx], 1),
            "sim_min_val": round(min(sim_points), 1),
            "lab_min_val": round(min(lab_points), 1),
            "trajectory": [
                {"t_h": round(t_points[i], 1),
                 "sim": round(sim_points[i], 1),
                 "lab": round(lab_points[i], 1)}
                for i in range(len(t_points))
            ],
        }
        results[str(b)] = row

    out = {
        "title": "R121b PAA trajectory shape probe",
        "batches": results,
        "hypotheses": [
            "H1: 时序错位——引擎 PAA 峰值早于化验峰值（peak_lag_h > 0）→ 4h 滞后不足",
            "H2: 幅值偏差——引擎在高 μp 系统性低估（Y_PAA_P 或 Y_PAA_X 系数偏小）",
            "H3: 形状失真——引擎 PAA 拐点早于化验（生长相过早转生产相）",
            "H4: 维持消耗过大——m_PAA*X 在高生物量时消耗 PAA 过快",
        ],
    }
    dst = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "runs", "p3", "paa_shape_probe.json")
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"Saved: {dst}", flush=True)
    # 打印摘要
    for b, r in results.items():
        print(f"batch {b}: μp={r['mu_p']} corr={r['paa_corr']} "
              f"sim_peak@{r['sim_peak_t']}h val={r['sim_peak_val']} "
              f"lab_peak@{r['lab_peak_t']}h val={r['lab_peak_val']} "
              f"lag={r['peak_lag_h']}h", flush=True)


if __name__ == "__main__":
    main()

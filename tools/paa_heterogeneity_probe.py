# -*- coding: utf-8 -*-
"""R121: PAA 批间异质机理探查。
R91 发现 corr(PAA 保真 r, μp) = -0.891：高 μp 批反相、低 μp 批近完美。
本探查对比反相批（22/23）与近完美批（36/60）的 PAA 动力学结构，
识别引擎 PAA 方程的结构误差来源。

PAA 方程（model.py L426-427）：
  dPAA/dt = Fpaa*PAA_c/V - Y_PAA_P*dP/dt - Y_PAA_X*X - m_PAA*X - PAA*dilution/V

输出：
- 各批 PAA 轨迹 vs 化验的相关系数（已知结论复验）
- 各批 P 通道残差（引擎 vs 化验）→ 判断 dP/dt 是否为误差源
- 各批 PAA 生产项（Y_PAA_P*dP/dt）与消耗项（m_PAA*X）的量级对比
- 假设检验：如果反相批的 P 残差也大 → P 通道结构误差传导至 PAA
"""
import io
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))

import numpy as np
import pandas as pd

from simulate import simulate_open_loop, load_batch, build_initial_state
from calibration import calib_params

BATCHES = [22, 23, 36, 60]  # 22/23 反相, 36/60 近完美


def main():
    results = []
    for b in BATCHES:
        d = load_batch(b)
        params = calib_params(b)
        sim, _ = simulate_open_loop(b, params)
        sim = sim.copy()

        # 化验锚点
        paa_lab = pd.to_numeric(d["PAA_offline"], errors="coerce")
        p_lab = pd.to_numeric(d["P_offline"], errors="coerce")
        t_lab = d["time_h"]

        # 引擎轨迹在化验时点的值（4h 滞后）
        t_sim = sim["time_h"].to_numpy(float)
        paa_sim_at = np.interp(
            [float(t_lab.iloc[i]) - 4.0 for i in range(len(d))],
            t_sim, sim["PAA"].to_numpy(float))
        p_sim_at = np.interp(
            [float(t_lab.iloc[i]) - 4.0 for i in range(len(d))],
            t_sim, sim["P"].to_numpy(float))

        # 有效锚点（t>20, 有限化验值）
        mask = (t_lab > 20) & paa_lab.notna() & (paa_lab != 0)
        r_paa = np.corrcoef(paa_sim_at[mask], paa_lab[mask])[0, 1]
        r_p = np.corrcoef(p_sim_at[mask], p_lab[mask])[0, 1] if p_lab[mask].notna().any() else float("nan")

        # PAA 生产/消耗项量级
        X_at = np.interp(t_sim, t_sim, sim["X"].to_numpy(float))
        dP_dt = np.gradient(sim["P"].to_numpy(float), t_sim)
        # 从 params 读系数
        # calib_params 返回 dict, 但 model 用的 par 数组
        # 简化：用 engine 输出的 PAA 变化率反推
        dPAA_dt = np.gradient(sim["PAA"].to_numpy(float), t_sim)

        # P 通道残差 RMSE
        p_rmse = float(np.sqrt(np.mean((p_sim_at[mask] - p_lab[mask])**2))) if mask.sum() > 2 else float("nan")

        row = {
            "batch": b,
            "mu_p": round(float(params.get("mup", float("nan"))), 4),
            "paa_corr": round(float(r_paa), 3),
            "p_corr": round(float(r_p), 3) if np.isfinite(r_p) else None,
            "p_rmse": round(p_rmse, 1) if np.isfinite(p_rmse) else None,
            "paa_max_sim": round(float(np.max(sim["PAA"])), 1),
            "paa_max_lab": round(float(np.max(paa_lab[mask])), 1) if mask.sum() > 0 else None,
            "paa_mean_sim": round(float(np.mean(sim["PAA"])), 1),
            "paa_mean_lab": round(float(np.mean(paa_lab[mask])), 1) if mask.sum() > 0 else None,
            "n_anchors": int(mask.sum()),
        }
        results.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)

    # 汇总分析
    out = {
        "title": "R121 PAA batch heterogeneity mechanism probe",
        "batches": results,
        "analysis": [
            "对比反相批(22/23)与近完美批(36/60)的 P 通道残差——",
            "若反相批 P 残差也大 → P 通道结构误差传导至 PAA（dP/dt 项）",
            "若反相批 P 残差小但 PAA 残差大 → PAA 方程本身结构误差",
        ],
    }
    dst = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "runs", "p3", "paa_heterogeneity_probe.json")
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"Saved: {dst}", flush=True)


if __name__ == "__main__":
    main()

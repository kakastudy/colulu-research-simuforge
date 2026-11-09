# -*- coding: utf-8 -*-
"""D6 独立健康视图（V1+）：用黄金回归基线参数（非 calib_params）对全部 12 黄金批
做逐通道健康评估，含 PAA 通道。

与 trajectory_metrics.py 的区别：
- trajectory_metrics.py: 用 calib_params（逐批校准），只覆盖在线通道，给原始指标
- D6: 用黄金回归 COMBINED 基线参数（独立于校准），覆盖全部通道（含 PAA/NH3/vis），
  给健康分级（healthy/warning/critical）和总体判决

健康分级（nRMSE = RMSE / lab_mean × 100%）:
  Healthy:   nRMSE < 5%
  Warning:   nRMSE 5-15%
  Critical:  nRMSE > 15%

批级健康:
  Healthy:   平均 nRMSE < 8% 且 0 critical 通道
  Warning:   平均 nRMSE 8-15% 或 1-2 critical 通道
  Critical:  平均 nRMSE > 15% 或 > 2 critical 通道

总体判决:
  Healthy:   > 80% 通道-批对 healthy
  Warning:   50-80% healthy
  Critical:  < 50% healthy

CLI: python d6_health_view.py [--out runs/p3/d6_health_view.json]
"""
import argparse
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from simulate import simulate_open_loop

# 黄金集参数与批列表：单一事实源 tools/golden_params.py（R131 去重复）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from golden_params import COMBINED, GOLDEN_ALL as GOLDEN  # noqa: E402

# 通道映射：channel_name -> (sim_col, v3_col)
# 在线通道：sim 和 V3 都有
# 离线通道：V3 有 *_offline，sim 有对应内部变量
CHANNEL_MAP = {
    "DO2": ("DO2", "DO2"),
    "P": ("P", "P"),
    "T": ("T", "T"),
    "pH": ("pH", "pH"),
    "V": ("V", "V"),
    "Wt": ("Wt", "Wt"),
    "OUR": ("OUR", "OUR"),
    "CER": ("CER", "CER"),
    "CO2outgas": ("CO2outgas", "CO2outgas"),
    "O2": ("O2", "O2"),
    # Q 通道移除（R129p6）：V3 Q 是 V3 输入 (Fc, Fh, T) 的计算量
    # （逐批 R²>0.96），不是反应罐总热产率的独立测量。
    # sim Q (y[8]/1000) 是 ODE 模型的总热流率，两者物理含义不同，
    # 逐批均值比非恒定（0.02-0.28），线性回归斜率为负。
    # 不应直接比较，故从 D6 健康视图移除。
    "X_offline": ("X", "X_offline"),
    "P_offline": ("P", "P_offline"),
    "PAA_offline": ("PAA", "PAA_offline"),
    "NH3_offline": ("NH3", "NH3_offline"),
    "Viscosity_offline": ("vis", "Viscosity_offline"),
}


def health_grade(nrmse):
    if nrmse < 5:
        return "healthy"
    elif nrmse < 15:
        return "warning"
    else:
        return "critical"


def compute_channel_metrics(sim, v3, sim_col, v3_col):
    """计算单通道 RMSE/nRMSE/bias。处理 NaN 值（离线通道稀疏采样）。"""
    sim_vals = sim[sim_col].to_numpy(float)
    lab_vals = v3[v3_col].to_numpy(float)
    n = min(len(sim_vals), len(lab_vals))
    sim_vals = sim_vals[:n]
    lab_vals = lab_vals[:n]

    # 过滤 NaN：只保留 lab 有值的时刻
    valid = ~np.isnan(lab_vals)
    if not np.any(valid):
        return {"rmse": 0.0, "nrmse": 0.0, "bias": 0.0, "lab_mean": 0.0,
                "valid_count": 0, "health": "no_data"}

    sim_vals = sim_vals[valid]
    lab_vals = lab_vals[valid]

    diff = sim_vals - lab_vals
    rmse = float(np.sqrt(np.mean(diff ** 2)))
    lab_mean = float(np.mean(lab_vals))
    nrmse = (rmse / lab_mean) * 100 if lab_mean > 1e-10 else 0.0
    bias = float(np.mean(diff))
    return {"rmse": round(rmse, 4), "nrmse": round(nrmse, 2),
            "bias": round(bias, 4), "lab_mean": round(lab_mean, 4),
            "valid_count": int(np.sum(valid)), "health": health_grade(nrmse)}


def main():
    parser = argparse.ArgumentParser(description="D6 独立健康视图")
    parser.add_argument("--out", default=None, help="输出 JSON 路径")
    args = parser.parse_args()

    out_path = args.out or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "runs", "p3", "d6_health_view.json")

    print("=" * 80)
    print("D6 独立健康视图 — 黄金回归基线参数（非 calib_params）")
    print("=" * 80)

    results = {}
    all_pair_health = []

    for b in GOLDEN:
        v3 = pd.read_csv(f"data/processed/batches/batch_{b:02d}.csv")
        cp = COMBINED[b]

        # 构建参数
        params = {"mux": cp["mux"], "mup": cp["mup"], "alpha_kla": cp.get("alpha_kla", 85.0),
                  "PAA_c": cp.get("PAA_c", 530000.0), "N_conc_paa": 150000.0, "c_oil": 1000.0,
                  "dist_flag": 1, "dist_tcin_asym": cp["dist_tcin_asym"], "m_s": cp["m_s"]}
        if "m_s_schedule" in cp:
            params["m_s_schedule"] = cp["m_s_schedule"]
        if "biomass_death_rate" in cp:
            params["biomass_death_rate"] = cp["biomass_death_rate"]
            params["death_start"] = cp["death_start"]
        if "q_co2" in cp:
            params["q_co2"] = cp["q_co2"]
        if "Y_NX" in cp:
            params["Y_NX"] = cp["Y_NX"]
        if "Y_NP" in cp:
            params["Y_NP"] = cp["Y_NP"]
        if "vis_scale" in cp:
            params["vis_scale"] = cp["vis_scale"]
        if "m_paa" in cp:
            params["m_paa"] = cp["m_paa"]
        if "Y_O2_X" in cp:
            params["Y_O2_X"] = cp["Y_O2_X"]
        if "Y_O2_P" in cp:
            params["Y_O2_P"] = cp["Y_O2_P"]
        if "m_O2_X" in cp:
            params["m_O2_X"] = cp["m_O2_X"]
        if "mu_h_scale" in cp:
            params["mu_h_scale"] = cp["mu_h_scale"]
        if "late_death_rate" in cp:
            params["late_death_rate"] = cp["late_death_rate"]
            params["mu_death_ref"] = cp.get("mu_death_ref", 0.02)
            params["death_recycle"] = cp.get("death_recycle", 0.0)

        sim, _ = simulate_open_loop(b, params)

        batch_channels = {}
        critical_count = 0
        nrmse_sum = 0.0
        nrmse_count = 0

        for ch_name, (sim_col, v3_col) in CHANNEL_MAP.items():
            if sim_col not in sim.columns or v3_col not in v3.columns:
                continue
            metrics = compute_channel_metrics(sim, v3, sim_col, v3_col)
            batch_channels[ch_name] = metrics
            if metrics["health"] in ("healthy", "warning", "critical"):
                nrmse_sum += metrics["nrmse"]
                nrmse_count += 1
                if metrics["health"] == "critical":
                    critical_count += 1
            if metrics["health"] in ("healthy", "warning", "critical"):
                all_pair_health.append(metrics["health"])

        avg_nrmse = nrmse_sum / nrmse_count if nrmse_count > 0 else 0.0

        # 批级健康
        if avg_nrmse < 8 and critical_count == 0:
            batch_health = "healthy"
        elif avg_nrmse > 15 or critical_count > 2:
            batch_health = "critical"
        else:
            batch_health = "warning"

        print(f"  Batch {b:2d}: {batch_health:>8s}  avg_nRMSE={avg_nrmse:6.2f}  "
              f"critical={critical_count}")

        results[str(b)] = {
            "batch_health": batch_health,
            "avg_nrmse": round(avg_nrmse, 2),
            "critical_count": critical_count,
            "channels": batch_channels,
        }

    # 总体判决
    total_pairs = len(all_pair_health)
    healthy_pairs = sum(1 for h in all_pair_health if h == "healthy")
    healthy_pct = healthy_pairs / total_pairs * 100 if total_pairs > 0 else 0.0

    if healthy_pct > 80:
        overall = "healthy"
    elif healthy_pct >= 50:
        overall = "warning"
    else:
        overall = "critical"

    print("-" * 80)
    print(f"  Overall: {overall}  healthy={healthy_pairs}/{total_pairs} ({healthy_pct:.1f}%)")
    print("=" * 80)

    output = {
        "overall_verdict": overall,
        "healthy_pairs": healthy_pairs,
        "total_pairs": total_pairs,
        "healthy_pct": round(healthy_pct, 1),
        "batches": results,
    }

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"Saved: {out_path}")


if __name__ == "__main__":
    main()

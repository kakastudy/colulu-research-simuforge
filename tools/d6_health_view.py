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
from golden_params import build_params  # R132: 直接取单一源的装配函数，不再经 diag 中转

# 黄金集参数与批列表：单一事实源 tools/golden_params.py（R131 去重复）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from golden_params import COMBINED, GOLDEN_ALL as GOLDEN  # noqa: E402

# 通道映射：channel_name -> (sim_col, v3_col)
# 在线通道：sim 和 V3 都有
# 离线通道：V3 有 *_offline，sim 有对应内部变量
# R132 (S0.2)：离线化验通道必须做 4h 滞后对齐。
# 依据 indpensim_run.m L49 `Off_line_delay = 4`——化验值在取样后 4h 才有读数，
# 因此 lab(t) 对应的是 sim 在 t+4h 的状态。R131 的 r131_harness 早已按此口径
# （OFFLINE_DELAY_H=4）评估，而本脚本此前按索引直接对齐，两套口径算同一件事，
# 导致 D6 的离线通道数字系统性偏高、且与报告里的 12 批数字不可比。
OFFLINE_DELAY_H = 4.0
OFFLINE_CHANNELS = {"X_offline", "P_offline", "PAA_offline",
                    "NH3_offline", "Viscosity_offline"}

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


def compute_channel_metrics(sim, v3, sim_col, v3_col, lag_h=0.0):
    """计算单通道 RMSE/nRMSE/bias。

    lag_h=0    → 索引对齐（历史口径；仿真与 V3 网格同为 0.2h，长度差 1 行）
    lag_h>0    → 时间插值对齐：lab(t) ↔ sim(t+lag_h)，用于离线化验通道

    注意 lag_h>0 时，批末 t+lag 会越过仿真终点，np.interp 按端点值外推
    （与 r131_harness 的 np.interp 行为一致，不另行外推）。
    """
    if lag_h:
        t_lab = v3["time_h"].to_numpy(float)
        lab_all = v3[v3_col].to_numpy(float)
        valid = np.isfinite(lab_all)
        if not np.any(valid):
            return {"rmse": 0.0, "nrmse": 0.0, "bias": 0.0, "lab_mean": 0.0,
                    "valid_count": 0, "health": "no_data"}
        t_q = t_lab[valid] + lag_h
        sim_vals = np.interp(t_q, sim["time_h"].to_numpy(float),
                             sim[sim_col].to_numpy(float))
        lab_vals = lab_all[valid]
    else:
        sim_vals = sim[sim_col].to_numpy(float)
        lab_vals = v3[v3_col].to_numpy(float)
        n = min(len(sim_vals), len(lab_vals))
        sim_vals = sim_vals[:n]
        lab_vals = lab_vals[:n]
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


def eval_batch(job):
    """单批评估 → (批号, 批结果, 通道-批健康对)。job=(批号, 是否做离线滞后)。

    用元组传参而非全局变量：Windows 下 multiprocessing 是 spawn，
    父进程设置的模块级全局不会被子进程继承（会在 8 核上静默退回无滞后口径）。
    """
    b, use_lag = job
    v3 = pd.read_csv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                  "data", "processed", "batches", f"batch_{b:02d}.csv"))
    params = build_params(COMBINED[b])
    sim, _ = simulate_open_loop(b, params)

    batch_channels = {}
    critical_count = 0
    nrmse_sum = 0.0
    nrmse_count = 0
    pairs = []

    for ch_name, (sim_col, v3_col) in CHANNEL_MAP.items():
        if sim_col not in sim.columns or v3_col not in v3.columns:
            continue
        lag = OFFLINE_DELAY_H if (use_lag and ch_name in OFFLINE_CHANNELS) else 0.0
        metrics = compute_channel_metrics(sim, v3, sim_col, v3_col, lag_h=lag)
        batch_channels[ch_name] = metrics
        if metrics["health"] in ("healthy", "warning", "critical"):
            nrmse_sum += metrics["nrmse"]
            nrmse_count += 1
            if metrics["health"] == "critical":
                critical_count += 1
            pairs.append(metrics["health"])

    avg_nrmse = nrmse_sum / nrmse_count if nrmse_count > 0 else 0.0
    if avg_nrmse < 8 and critical_count == 0:
        batch_health = "healthy"
    elif avg_nrmse > 15 or critical_count > 2:
        batch_health = "critical"
    else:
        batch_health = "warning"

    return b, {"batch_health": batch_health, "avg_nrmse": round(avg_nrmse, 2),
               "critical_count": critical_count, "channels": batch_channels}, pairs


def main():
    parser = argparse.ArgumentParser(description="D6 独立健康视图")
    parser.add_argument("--out", default=None, help="输出 JSON 路径")
    parser.add_argument("--serial", action="store_true", help="串行执行（对照用）")
    parser.add_argument("--lag", action="store_true",
                        help="离线通道施加 4h 化验滞后对齐（对照口径；见下方说明）")
    parser.add_argument("--no-lag", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    out_path = args.out or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "runs", "p3", "d6_health_view.json")

    # R132 实测结论：**4h 一刀切不是改进**。全量 86 批：
    #   无滞后 417/1290 (32.3%)  vs  4h 滞后 411/1290 (31.9%)
    # 分通道看是混合的——P_offline 15.0→13.7、PAA 29.6→28.9 变好，
    # X_offline 23.5→25.1、Viscosity 42.5→48.8 变差。说明不同化验项的
    # 实际等效滞后不同，不能共用一个 4h。
    # 因此默认保持历史口径（与 R131 报告可比），4h 滞后作为对照开关保留；
    # 逐通道等效滞后由 tools/r132_channel_classifier.py 的数据估计给出。
    use_lag = bool(args.lag)
    print("=" * 80)
    print("D6 独立健康视图 — 黄金回归基线参数（非 calib_params）")
    print(f"离线通道对齐：{'4h 滞后（R132 新口径，与 r131_harness 一致）' if use_lag else '无滞后（历史口径）'}")
    print("=" * 80)

    jobs = [(b, use_lag) for b in GOLDEN]
    if args.serial:
        out = [eval_batch(j) for j in jobs]
    else:
        from multiprocessing import Pool
        with Pool(min(8, os.cpu_count() or 1)) as pool:
            out = pool.map(eval_batch, jobs, chunksize=1)

    results = {}
    all_pair_health = []
    for b, rec, pairs in out:
        results[str(b)] = rec
        all_pair_health.extend(pairs)
        print(f"  Batch {b:2d}: {rec['batch_health']:>8s}  avg_nRMSE={rec['avg_nrmse']:6.2f}  "
              f"critical={rec['critical_count']}")

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

    output = {"offline_delay_h": OFFLINE_DELAY_H if use_lag else 0.0,
              "overall_verdict": overall, "healthy_pairs": healthy_pairs,
              "total_pairs": total_pairs, "healthy_pct": round(healthy_pct, 1),
              "batches": results}
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"Saved: {out_path}")


if __name__ == "__main__":
    main()

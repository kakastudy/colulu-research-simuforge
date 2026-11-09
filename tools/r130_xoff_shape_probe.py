# -*- coding: utf-8 -*-
"""R130: X_offline 形态诊断探针 —— 量化 sim X 轨迹 vs V3 X_offline 的形状失配。

背景（goal_backtrace_check / deepening_plan R129）：
- X_offline 通道是 D6 健康视图唯一 remaining critical（nRMSE ~24%），
  且与产量结构性耦合（"改善必破坏产量"）。
- 根因候选：生物量轨迹形状错误（生长相过快/衰亡缺失/生产相不衰减）。

本探针对 12 原始黄金批用当前 COMBINED 参数回放，输出：
- sim X 与 V3 X_offline 的对齐偏差（nRMSE、corr、lag）
- 形状特征对比：峰值时间/峰值/最大增长率/末段衰减率
- 形态失配分类（早峰/晚峰/幅值偏差/衰减缺失）

用法：python r130_xoff_shape_probe.py [--out runs/p3/r130_xoff_shape_probe.json]
"""
import argparse
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from simulate import simulate_open_loop  # noqa: E402

COMBINED = {
    8:  {"mux": 0.47, "mup": 0.041, "dist_tcin_asym": 10, "m_s": 0.029,
          "biomass_death_rate": 0.001, "death_start": 100, "q_co2": 0.12, "Y_NX": 10, "Y_NP": 80, "alpha_kla": 90, "vis_scale": 0.9, "PAA_c": 530000.0, "m_paa": 1.0, "Y_O2_X": 800, "Y_O2_P": 200, "m_O2_X": 15},
    11: {"mux": 0.41, "mup": 0.041, "dist_tcin_asym": 10, "m_s": 0.020, "q_co2": 0.11, "Y_NX": 10, "Y_NP": 80, "alpha_kla": 110, "vis_scale": 0.9, "PAA_c": 530000.0, "m_paa": 0.7, "Y_O2_X": 800, "Y_O2_P": 80, "m_O2_X": 15},
    16: {"mux": 0.41, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.025,
          "biomass_death_rate": 0.005, "death_start": 0, "q_co2": 0.14, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 75, "vis_scale": 0.9, "PAA_c": 400000.0, "m_paa": 0.5, "Y_O2_X": 800, "Y_O2_P": 200, "m_O2_X": 17.5},
    22: {"mux": 0.35, "mup": 0.065, "dist_tcin_asym": 20, "m_s": 0.029,
          "m_s_schedule": [(110, 0.010)], "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85,
          "mu_h_scale": 3.5},
    23: {"mux": 0.35, "mup": 0.070, "dist_tcin_asym": 10, "m_s": 0.029,
          "biomass_death_rate": 0.0005, "death_start": 200, "q_co2": 0.1, "Y_NX": 15, "Y_NP": 60, "alpha_kla": 110, "vis_scale": 0.9, "PAA_c": 530000.0, "m_paa": 1.0, "Y_O2_X": 650, "Y_O2_P": 200, "m_O2_X": 15,
          "mu_h_scale": 3.5},
    27: {"mux": 0.36, "mup": 0.040, "dist_tcin_asym": 15, "m_s": 0.029,
          "m_s_schedule": [(140, 0.018)], "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85, "vis_scale": 0.9, "PAA_c": 530000.0, "m_paa": 1.0, "Y_O2_X": 650, "Y_O2_P": 160, "m_O2_X": 15},
    36: {"mux": 0.47, "mup": 0.045, "dist_tcin_asym": 10, "m_s": 0.010, "q_co2": 0.1, "Y_NX": 20, "Y_NP": 40, "alpha_kla": 130, "vis_scale": 0.8, "PAA_c": 530000.0, "m_paa": 0.7, "Y_O2_X": 650, "Y_O2_P": 160, "m_O2_X": 10},
    55: {"mux": 0.47, "mup": 0.055, "dist_tcin_asym": 20, "m_s": 0.025,
          "biomass_death_rate": 0.001, "death_start": 200, "q_co2": 0.11, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85, "PAA_c": 530000.0, "m_paa": 1.0, "Y_O2_X": 650, "Y_O2_P": 160, "m_O2_X": 15},
    60: {"mux": 0.47, "mup": 0.035, "dist_tcin_asym": 15, "m_s": 0.010, "q_co2": 0.1, "Y_NX": 20, "Y_NP": 40, "alpha_kla": 85, "PAA_c": 530000.0, "m_paa": 1.0, "Y_O2_X": 650, "Y_O2_P": 160, "m_O2_X": 15},
    80: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 18, "m_s": 0.029,
          "biomass_death_rate": 0.005, "death_start": 0, "q_co2": 0.13, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85, "vis_scale": 0.9, "PAA_c": 400000.0, "m_paa": 0.3, "Y_O2_X": 800, "Y_O2_P": 120, "m_O2_X": 17.5},
    91: {"mux": 0.39, "mup": 0.041, "dist_tcin_asym": 10, "m_s": 0.029,
          "biomass_death_rate": 0.005, "death_start": 200, "q_co2": 0.12, "Y_NX": 10, "Y_NP": 60, "alpha_kla": 90, "PAA_c": 530000.0, "m_paa": 0.1, "Y_O2_X": 650, "Y_O2_P": 160, "m_O2_X": 15},
    92: {"mux": 0.47, "mup": 0.041, "dist_tcin_asym": 18, "m_s": 0.029,
          "m_s_schedule": [(150, 0.015)],
          "biomass_death_rate": 0.005, "death_start": 200, "q_co2": 0.11, "Y_NX": 12, "Y_NP": 60, "alpha_kla": 130, "vis_scale": 0.9, "PAA_c": 530000.0, "m_paa": 0.7, "Y_O2_X": 650, "Y_O2_P": 160, "m_O2_X": 15},
}

GOLDEN = [8, 11, 16, 22, 23, 27, 36, 55, 60, 80, 91, 92]
LAG_H = 4.0  # 化验滞后口径（Off_line_delay=4，indpensim_run.m L49）


def shape_features(t, x):
    """从轨迹提取形状特征：峰值时间/峰值/最大增长率/末段衰减率。"""
    if len(x) < 3:
        return {}
    imax = int(np.argmax(x))
    dx = np.gradient(x, t)
    imax_g = int(np.argmax(dx))
    # 末段衰减率：最后 15% 时段的 dX/dt
    n = len(x)
    tail = slice(max(0, n - int(0.15 * n)), n)
    decay = float(np.mean(dx[tail])) if len(dx[tail]) else 0.0
    return {
        "t_peak_h": float(t[imax]), "x_peak": float(x[imax]),
        "max_growth_h": float(dx[imax_g]), "t_max_growth_h": float(t[imax_g]),
        "decay_tail": decay, "x_end": float(x[-1]), "t_end": float(t[-1]),
    }


def align_lag(sim_t, sim_x, v3_t, v3_x, lag=LAG_H):
    """sim 与 v3 按化验滞后对齐：v3(t) 对照 sim(t-lag)。"""
    sim_interp = np.interp(v3_t - lag, sim_t, sim_x, left=sim_x[0], right=sim_x[-1])
    mask = ~np.isnan(v3_x)
    return sim_interp[mask], v3_x[mask]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="runs/p3/r130_xoff_shape_probe.json")
    args = ap.parse_args()

    results = []
    for b in GOLDEN:
        v3 = pd.read_csv(f"data/processed/batches/batch_{b:02d}.csv")
        cp = COMBINED[b]
        params = {"dist_flag": 1}  # 验收脚本必带（时变扰动，缺则 pH 崩/S 累积假像）
        params.update(cp)
        sim, _ = simulate_open_loop(b, params=params)
        # sim 采样间隔 0.2h，V3 同
        sim_t = sim["time_h"].to_numpy(float)
        sim_x = sim["X"].to_numpy(float)
        v3_t = v3["time_h"].to_numpy(float)
        v3_x = pd.to_numeric(v3["X_offline"], errors="coerce").to_numpy(float)

        s_lag, v_lag = align_lag(sim_t, sim_x, v3_t, v3_x)
        if len(v_lag) >= 3:
            rmse = float(np.sqrt(np.mean((s_lag - v_lag) ** 2)))
            vmean = float(np.mean(v_lag))
            nrmse = rmse / vmean * 100 if vmean > 0 else 999.0
            corr = float(np.corrcoef(s_lag, v_lag)[0, 1])
        else:
            rmse = nrmse = corr = float("nan")

        f_sim = shape_features(sim_t, sim_x)
        f_v3 = shape_features(v3_t[~np.isnan(v3_x)], v3_x[~np.isnan(v3_x)])

        # 形态失配分类
        kind = "unknown"
        if f_sim and f_v3:
            dt_peak = f_sim["t_peak_h"] - f_v3["t_peak_h"]
            dx_peak = f_sim["x_peak"] - f_v3["x_peak"]
            if abs(dt_peak) > 12 and dt_peak > 0:
                kind = "late_peak"
            elif abs(dt_peak) > 12 and dt_peak < 0:
                kind = "early_peak"
            elif abs(dx_peak) > 2.0:
                kind = "amplitude"
            if f_sim["decay_tail"] > -0.01 and f_v3["decay_tail"] < -0.01:
                kind = "no_decay"  # sim 末段不衰减而 v3 衰减
            if abs(dt_peak) <= 12 and abs(dx_peak) <= 2.0:
                kind = "shape_ok"

        rec = {
            "batch": b, "n_offline": int(len(v_lag)),
            "nrmse_pct": round(nrmse, 2), "corr": round(corr, 3),
            "sim": {k: round(v, 3) for k, v in f_sim.items()},
            "v3": {k: round(v, 3) for k, v in f_v3.items()},
            "mismatch_kind": kind,
        }
        results.append(rec)
        print(f"b{b:>3d} n={rec['n_offline']:>2d} nRMSE={nrmse:6.1f}% corr={corr:5.2f} "
              f"{kind:<10s} | sim peak t={f_sim.get('t_peak_h', 0):6.1f}h x={f_sim.get('x_peak', 0):5.1f} "
              f"v3 peak t={f_v3.get('t_peak_h', 0):6.1f}h x={f_v3.get('x_peak', 0):5.1f} "
              f"| decay sim={f_sim.get('decay_tail', 0):+.3f} v3={f_v3.get('decay_tail', 0):+.3f}")

    n_late = sum(1 for r in results if r["mismatch_kind"] == "late_peak")
    n_early = sum(1 for r in results if r["mismatch_kind"] == "early_peak")
    n_amp = sum(1 for r in results if r["mismatch_kind"] == "amplitude")
    n_decay = sum(1 for r in results if r["mismatch_kind"] == "no_decay")
    n_ok = sum(1 for r in results if r["mismatch_kind"] == "shape_ok")
    print("-" * 100)
    print(f"失配分类: late_peak={n_late} early_peak={n_early} amplitude={n_amp} "
          f"no_decay={n_decay} shape_ok={n_ok}")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"results": results, "summary": {
            "n_late_peak": n_late, "n_early_peak": n_early, "n_amplitude": n_amp,
            "n_no_decay": n_decay, "n_shape_ok": n_ok, "lag_h": LAG_H}}, f, indent=2, ensure_ascii=False)
    print(f"Saved: {args.out}")


if __name__ == "__main__":
    main()

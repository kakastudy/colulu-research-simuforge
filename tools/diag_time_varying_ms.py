# -*- coding: utf-8 -*-
"""时变 m_s 诊断：探索 m_s 调度解耦崩溃与过度产 P。

假设：
- 早期 (t < T_switch): 高 m_s (0.029) → S 快速消耗 → CO2d 低 → 不崩溃
- 晚期 (t >= T_switch): 低 m_s (0.005) → S 积累 → P 匹配 V3

测试 batch 27, 92, 22, 60（当前 RMSE 最大贡献者）。
"""
import sys, os
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from simulate import simulate_open_loop, yield_metrics

# 各批次的基准参数（当前最优）
BASE_PARAMS = {
    27: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 15},
    92: {"mux": 0.47, "mup": 0.041, "dist_tcin_asym": 18},
    22: {"mux": 0.41, "mup": 0.070, "dist_tcin_asym": 20},
    60: {"mux": 0.47, "mup": 0.030, "dist_tcin_asym": 15},
}

# m_s 调度网格
T_SWITCH_GRID = [80, 100, 120, 140]
M_S_EARLY_GRID = [0.029]
M_S_LATE_GRID = [0.005, 0.010, 0.015, 0.020]

for b, base in BASE_PARAMS.items():
    d = pd.read_csv(f"data/processed/batches/batch_{b:02d}.csv")
    print(f"\n=== Batch {b}: Time-varying m_s scan ===", flush=True)
    print(f"  Base: mux={base['mux']}, mup={base['mup']}, dTcin={base['dist_tcin_asym']:+d}", flush=True)

    best_no_crash = None
    for t_switch in T_SWITCH_GRID:
        for ms_early in M_S_EARLY_GRID:
            for ms_late in M_S_LATE_GRID:
                params = {
                    "mux": base["mux"], "mup": base["mup"],
                    "alpha_kla": 85.0, "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0,
                    "dist_flag": 1, "dist_tcin_asym": base["dist_tcin_asym"],
                    "m_s_schedule": [(t_switch, ms_late)],
                    "m_s": ms_early,
                }
                try:
                    sim, _ = simulate_open_loop(b, params)
                    ym = yield_metrics(sim, d)
                    err = ym["rel_err_total"]
                    co2d_max = sim["CO2d"].max()
                    crashed = co2d_max > 7.57
                    status = "CRASH" if crashed else "ok"
                    if not crashed:
                        if best_no_crash is None or abs(err) < abs(best_no_crash["err"]):
                            best_no_crash = {"err": err, "t_switch": t_switch, "ms_early": ms_early, "ms_late": ms_late, "co2d": co2d_max}
                    print(f"  t_sw={t_switch:3d} ms_early={ms_early:.3f} ms_late={ms_late:.3f}: yield={err:+.1%} CO2d={co2d_max:.2f} {status}", flush=True)
                except Exception as e:
                    print(f"  t_sw={t_switch:3d} ms_early={ms_early:.3f} ms_late={ms_late:.3f}: ERROR {e}", flush=True)

    if best_no_crash:
        print(f"\n  Best no-crash: t_switch={best_no_crash['t_switch']} ms_early={best_no_crash['ms_early']:.3f} "
              f"ms_late={best_no_crash['ms_late']:.3f} yield={best_no_crash['err']:+.1%} CO2d={best_no_crash['co2d']:.2f}", flush=True)

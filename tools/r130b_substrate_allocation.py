# -*- coding: utf-8 -*-
"""R130b: 底物分配诊断 —— 量化 sim 的底物去向（生长/维持/产P）vs V3 实际。

背景：R130 探针发现 7/12 批 sim X 早峰（60-72h）vs V3 X_offline 晚峰（144-156h）。
假设：维持项 r_m0+r_m1 过早耗尽底物 → 生长提前停止；产量靠 mu_p 调参补偿。

本探针对 12 黄金批输出：
- S 轨迹（sim vs V3）+ S 耗尽时刻
- X 轨迹（sim vs V3_offline）+ 峰值时刻/幅值
- 底物账：总进料 - 末态 S = 总消耗；按 sim 内部速率分解（生长 r_se1/维持 r_m0+r_m1/产P Y_sP*mu_p*...）
- P 产率账：累计 P 生产（sim 内部 r_p 积分）vs 收获+末态

用法：python r130b_substrate_allocation.py
"""
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from simulate import simulate_open_loop  # noqa: E402

COMBINED = {
    8:  {"mux": 0.47, "mup": 0.041, "dist_tcin_asym": 10, "m_s": 0.029, "biomass_death_rate": 0.001, "death_start": 100, "q_co2": 0.12, "Y_NX": 10, "Y_NP": 80, "alpha_kla": 90, "vis_scale": 0.9, "PAA_c": 530000.0, "m_paa": 1.0, "Y_O2_X": 800, "Y_O2_P": 200, "m_O2_X": 15},
    11: {"mux": 0.41, "mup": 0.041, "dist_tcin_asym": 10, "m_s": 0.020, "q_co2": 0.11, "Y_NX": 10, "Y_NP": 80, "alpha_kla": 110, "vis_scale": 0.9, "PAA_c": 530000.0, "m_paa": 0.7, "Y_O2_X": 800, "Y_O2_P": 80, "m_O2_X": 15},
    16: {"mux": 0.41, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.025, "biomass_death_rate": 0.005, "death_start": 0, "q_co2": 0.14, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 75, "vis_scale": 0.9, "PAA_c": 400000.0, "m_paa": 0.5, "Y_O2_X": 800, "Y_O2_P": 200, "m_O2_X": 17.5},
    22: {"mux": 0.35, "mup": 0.065, "dist_tcin_asym": 20, "m_s": 0.029, "m_s_schedule": [(110, 0.010)], "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85, "mu_h_scale": 3.5},
    23: {"mux": 0.35, "mup": 0.070, "dist_tcin_asym": 10, "m_s": 0.029, "biomass_death_rate": 0.0005, "death_start": 200, "q_co2": 0.1, "Y_NX": 15, "Y_NP": 60, "alpha_kla": 110, "vis_scale": 0.9, "PAA_c": 530000.0, "m_paa": 1.0, "Y_O2_X": 650, "Y_O2_P": 200, "m_O2_X": 15, "mu_h_scale": 3.5},
    27: {"mux": 0.36, "mup": 0.040, "dist_tcin_asym": 15, "m_s": 0.029, "m_s_schedule": [(140, 0.018)], "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85, "vis_scale": 0.9, "PAA_c": 530000.0, "m_paa": 1.0, "Y_O2_X": 650, "Y_O2_P": 160, "m_O2_X": 15},
    36: {"mux": 0.47, "mup": 0.045, "dist_tcin_asym": 10, "m_s": 0.010, "q_co2": 0.1, "Y_NX": 20, "Y_NP": 40, "alpha_kla": 130, "vis_scale": 0.8, "PAA_c": 530000.0, "m_paa": 0.7, "Y_O2_X": 650, "Y_O2_P": 160, "m_O2_X": 10},
    55: {"mux": 0.47, "mup": 0.055, "dist_tcin_asym": 20, "m_s": 0.025, "biomass_death_rate": 0.001, "death_start": 200, "q_co2": 0.11, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85, "PAA_c": 530000.0, "m_paa": 1.0, "Y_O2_X": 650, "Y_O2_P": 160, "m_O2_X": 15},
    60: {"mux": 0.47, "mup": 0.035, "dist_tcin_asym": 15, "m_s": 0.010, "q_co2": 0.1, "Y_NX": 20, "Y_NP": 40, "alpha_kla": 85, "PAA_c": 530000.0, "m_paa": 1.0, "Y_O2_X": 650, "Y_O2_P": 160, "m_O2_X": 15},
    80: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 18, "m_s": 0.029, "biomass_death_rate": 0.005, "death_start": 0, "q_co2": 0.13, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85, "vis_scale": 0.9, "PAA_c": 400000.0, "m_paa": 0.3, "Y_O2_X": 800, "Y_O2_P": 120, "m_O2_X": 17.5},
    91: {"mux": 0.39, "mup": 0.041, "dist_tcin_asym": 10, "m_s": 0.029, "biomass_death_rate": 0.005, "death_start": 200, "q_co2": 0.12, "Y_NX": 10, "Y_NP": 60, "alpha_kla": 90, "PAA_c": 530000.0, "m_paa": 0.1, "Y_O2_X": 650, "Y_O2_P": 160, "m_O2_X": 15},
    92: {"mux": 0.47, "mup": 0.041, "dist_tcin_asym": 18, "m_s": 0.029, "m_s_schedule": [(150, 0.015)], "biomass_death_rate": 0.005, "death_start": 200, "q_co2": 0.11, "Y_NX": 12, "Y_NP": 60, "alpha_kla": 130, "vis_scale": 0.9, "PAA_c": 530000.0, "m_paa": 0.7, "Y_O2_X": 650, "Y_O2_P": 160, "m_O2_X": 15},
}

GOLDEN = [8, 11, 16, 22, 23, 27, 36, 55, 60, 80, 91, 92]


def main():
    out = {"batches": {}}
    for b in GOLDEN:
        v3 = pd.read_csv(f"data/processed/batches/batch_{b:02d}.csv")
        sim, _ = simulate_open_loop(b, params={"dist_flag": 1, **COMBINED[b]})
        sim_t = sim["time_h"].to_numpy(float)
        sim_s = sim["S"].to_numpy(float)
        sim_x = sim["X"].to_numpy(float)
        v3_t = v3["time_h"].to_numpy(float)
        v3_s = v3["S"].to_numpy(float)
        v3_x = pd.to_numeric(v3["X_offline"], errors="coerce").to_numpy(float)
        v3_p = v3["P"].to_numpy(float)

        # S 耗尽时刻（sim S < 0.5 g/L 首次）
        s_min_idx = int(np.argmin(sim_s))
        s_drain = sim_t[s_min_idx] if sim_s[s_min_idx] < 1.0 else float("nan")
        # X 峰值
        x_peak_idx = int(np.argmax(sim_x))
        x_peak_t = sim_t[x_peak_idx]
        x_peak_v = sim_x[x_peak_idx]
        v3_xm = v3_x[~np.isnan(v3_x)]
        v3_x_peak_t = v3_t[~np.isnan(v3_x)][int(np.argmax(v3_xm))] if len(v3_xm) else float("nan")
        v3_x_peak_v = float(np.nanmax(v3_x)) if np.any(~np.isnan(v3_x)) else float("nan")

        # 底物账（积分近似：梯形）
        feed = (v3["Fs"] * v3["S"].iloc[0] if "S" in v3 else 0.0)  # 首行 S 为初始底物
        # 总进料（Fs*c_s + Foil*c_oil + 初始 S*V）
        feed_total = float((v3["Fs"] * 600.0).sum() * 0.2 + (v3["Foil"] * 1000.0).sum() * 0.2
                           + v3["S"].iloc[0] * v3["V"].iloc[0])
        s_end = sim_s[-1] * sim["V"].iloc[-1]
        s_consumed = feed_total - s_end
        # P 产出（收获+末态）
        p_harvest = float((-v3["Fremoved"] * v3["P"]).sum() * 0.2)
        p_end = float(v3["P"].iloc[-1] * v3["V"].iloc[-1])
        p_total = p_harvest + p_end
        # 底物→P 的化学计量（Y_sP=0.9 g/g）
        s_to_p = p_total * 0.9
        s_to_growth_estimate = s_consumed - s_to_p

        rec = {
            "sim_s_drain_h": round(s_drain, 1), "sim_s_min": round(float(sim_s.min()), 3),
            "sim_x_peak_t": round(x_peak_t, 1), "sim_x_peak": round(x_peak_v, 2),
            "v3_x_peak_t": round(float(v3_x_peak_t), 1), "v3_x_peak": round(float(v3_x_peak_v), 2),
            "feed_total_g": round(feed_total, 1), "s_consumed_g": round(s_consumed, 1),
            "p_total_g": round(p_total, 1), "s_to_p_g": round(s_to_p, 1),
            "s_to_growth_estimate_g": round(s_to_growth_estimate, 1),
            "growth_frac_pct": round(100 * s_to_growth_estimate / s_consumed, 1) if s_consumed > 0 else 0.0,
        }
        out["batches"][str(b)] = rec
        print(f"b{b:>3d} S耗尽@{s_drain:6.1f}h X峰@{x_peak_t:6.1f}h({x_peak_v:5.1f}) "
              f"v3X峰@{v3_x_peak_t:6.1f}h({v3_x_peak_v:5.1f}) | 进料{feed_total:7.0f}g "
              f"消耗{s_consumed:7.0f}g P{p_total:6.1f}g 生长估{s_to_growth_estimate:7.0f}g({rec['growth_frac_pct']:.0f}%)")

    with open("runs/p3/r130b_substrate_allocation.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print("Saved: runs/p3/r130b_substrate_allocation.json")


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""R130c: V3 底物分配反演 —— 用化验轨迹推断真实底物去向（生长/产P/维持）。

思路：V3 数据有 X_offline（生物量）、P（产物）、S（底物）轨迹 + 进料。
总底物消耗 = 进料 + 初始 S·V - 末态 S·V。
生长底物 ≈ ΔX_biomass × Y_sX（Y_sX=1.85 g/g，模型参数）
产P底物 ≈ ΔP × Y_sP（Y_sP=0.9 g/g）
维持底物 = 总消耗 - 生长 - 产P（残差，含内源代谢/损失）

对比 sim 的分配（用模型内部速率积分），找出结构性差异。

用法：python r130c_v3_substrate_split.py
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
Y_SX = 1.85
Y_SP = 0.9
DT = 0.2


def main():
    out = {"batches": {}}
    for b in GOLDEN:
        v3 = pd.read_csv(f"data/processed/batches/batch_{b:02d}.csv")
        sim, _ = simulate_open_loop(b, params={"dist_flag": 1, **COMBINED[b]})

        # ---- V3 底物账 ----
        feed_g = float((v3["Fs"] * 600.0).sum() * DT + (v3["Foil"] * 1000.0).sum() * DT)
        s_init = float(v3["S"].iloc[0]) * float(v3["V"].iloc[0])
        s_end = float(v3["S"].iloc[-1]) * float(v3["V"].iloc[-1])
        s_consumed = feed_g + s_init - s_end

        # V3 生物量增量（X_offline 首末，插值到 t=0 与末态）
        xoff = pd.to_numeric(v3["X_offline"], errors="coerce")
        x_first = float(xoff.dropna().iloc[0])
        x_last = float(xoff.dropna().iloc[-1])
        x_v = float(v3["V"].iloc[0])
        biomass_g_init = x_first * x_v
        biomass_g_end = x_last * float(v3["V"].iloc[-1])
        biomass_delta = biomass_g_end - biomass_g_init
        s_to_growth = biomass_delta * Y_SX

        # V3 P 产出
        p_harvest = float((-v3["Fremoved"] * v3["P"]).sum() * DT)
        p_end = float(v3["P"].iloc[-1]) * float(v3["V"].iloc[-1])
        p_total = p_harvest + p_end
        s_to_p = p_total * Y_SP

        s_maint_v3 = s_consumed - s_to_growth - s_to_p

        # ---- sim 底物账（内部速率积分近似：用末段差分） ----
        sim_x = sim["X"].to_numpy(float)
        sim_v = sim["V"].to_numpy(float)
        biomass_sim_end = sim_x[-1] * sim_v[-1]
        biomass_sim_init = sim_x[0] * sim_v[0]
        biomass_delta_sim = biomass_sim_end - biomass_sim_init
        s_to_growth_sim = biomass_delta_sim * Y_SX
        s_to_p_sim = p_total * Y_SP  # sim 产量与 V3 近似一致（校准后）
        s_maint_sim = s_consumed - s_to_growth_sim - s_to_p_sim

        rec = {
            "s_consumed_g": round(s_consumed, 0),
            "v3_growth_g": round(s_to_growth, 0), "v3_p_g": round(s_to_p, 0),
            "v3_maint_g": round(s_maint_v3, 0),
            "v3_maint_pct": round(100 * s_maint_v3 / s_consumed, 1) if s_consumed > 0 else 0.0,
            "sim_growth_g": round(s_to_growth_sim, 0), "sim_maint_g": round(s_maint_sim, 0),
            "sim_maint_pct": round(100 * s_maint_sim / s_consumed, 1) if s_consumed > 0 else 0.0,
            "biomass_delta_v3": round(biomass_delta, 0), "biomass_delta_sim": round(biomass_delta_sim, 0),
        }
        out["batches"][str(b)] = rec
        print(f"b{b:>3d} 消耗{s_consumed:8.0f}g | V3: 生长{s_to_growth:7.0f}({100*s_to_growth/s_consumed:4.0f}%) "
              f"产P{s_to_p:6.0f}({100*s_to_p/s_consumed:4.0f}%) 维持{s_maint_v3:7.0f}({rec['v3_maint_pct']:4.1f}%) "
              f"| sim: 生长{s_to_growth_sim:7.0f}({100*s_to_growth_sim/s_consumed:4.0f}%) 维持{s_maint_sim:7.0f}({rec['sim_maint_pct']:4.1f}%) "
              f"| ΔX v3={biomass_delta:6.0f}g sim={biomass_delta_sim:6.0f}g")

    with open("runs/p3/r130c_v3_substrate_split.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print("Saved: runs/p3/r130c_v3_substrate_split.json")


if __name__ == "__main__":
    main()

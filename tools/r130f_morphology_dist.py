# -*- coding: utf-8 -*-
"""R130f: 形态分布诊断 —— sim 的 A0/A1/A3/A4 分布 vs V3 隐含分布。

V3 没有直接形态数据，但 X_offline 是总生物量。形态分布影响：
- A0（年轻菌丝）→ 生长速率 r_e1
- A3/A4（老/液泡化）→ 衰亡/降解
- 生产速率 r_p 依赖 v_a1（A1 的液泡体积）

输出关键时段的形态分布，判断 sim 是否「过度年轻」（A0/A1 过多，A3/A4 过少）。
"""
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
    out = {}
    for b in GOLDEN:
        sim, _ = simulate_open_loop(b, params={"dist_flag": 1, **COMBINED[b]})
        # 采样关键时段
        for kk in [50, 100, 150, 200, 230]:
            sub = sim[(sim['time_h'] >= kk) & (sim['time_h'] < kk + 10)]
            if len(sub) == 0:
                continue
            r = sub.iloc[len(sub) // 2]
            x = r['X']
            if x > 0:
                out[f"b{b}_t{kk}"] = {
                    "A0%": round(100 * r['A0'] / x, 1),
                    "A1%": round(100 * r['A1'] / x, 1),
                    "A3%": round(100 * r['A3'] / x, 1),
                    "A4%": round(100 * r['A4'] / x, 1),
                    "X": round(x, 1),
                }
    # 打印
    for k in sorted(out.keys()):
        print(f"{k:>10s} X={out[k]['X']:5.1f} A0={out[k]['A0%']:5.1f}% A1={out[k]['A1%']:5.1f}% A3={out[k]['A3%']:5.1f}% A4={out[k]['A4%']:5.1f}%")
    import json
    with open("runs/p3/r130f_morphology_dist.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print("Saved: runs/p3/r130f_morphology_dist.json")


if __name__ == "__main__":
    main()

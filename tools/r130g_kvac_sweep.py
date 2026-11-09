# -*- coding: utf-8 -*-
"""R130g: k_vac 液泡化扫描 —— 量化 A1→A3 转移对产量与 X 轨迹的影响。

扫描 k_vac ∈ {0, 0.005, 0.01, 0.02, 0.03, 0.05}，输出：
- yield_err（红线 ±5%）
- X 峰值/末值/衰减率
- A3/A4 占比（形态学补全验证）
- P 峰值/末值

用法：python r130g_kvac_sweep.py
"""
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from simulate import simulate_open_loop, yield_metrics  # noqa: E402

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
KVACS = [0.0, 0.005, 0.01, 0.02, 0.03, 0.05]


def main():
    out = {"results": []}
    for b in GOLDEN:
        v3 = pd.read_csv(f"data/processed/batches/batch_{b:02d}.csv")
        for kvac in KVACS:
            params = {"dist_flag": 1, "k_vac": kvac, **COMBINED[b]}
            try:
                sim, _ = simulate_open_loop(b, params=params)
                ym = yield_metrics(sim, v3)
                err = ym["rel_err_total"]
                x = sim["X"].to_numpy(float)
                dx = np.gradient(x, sim["time_h"].to_numpy(float))
                tail = slice(max(0, len(x) - int(0.15 * len(x))), len(x))
                decay = float(np.mean(dx[tail]))
                a3a4 = float((sim["A3"].iloc[-1] + sim["A4"].iloc[-1]) / max(sim["X"].iloc[-1], 1e-9) * 100)
                rec = {"batch": b, "k_vac": kvac, "yield_err": round(err, 4),
                       "x_peak": round(float(x.max()), 2), "x_last": round(float(x[-1]), 2),
                       "decay_tail": round(decay, 4), "a3a4_pct": round(a3a4, 1),
                       "p_last": round(float(sim["P"].iloc[-1]), 2)}
                out["results"].append(rec)
                flag = "★" if abs(err) <= 0.05 else " "
                print(f"b{b:>3d} kvac={kvac:.3f} {flag} yield={err:+7.2%} Xpk={rec['x_peak']:5.1f} "
                      f"Xlast={rec['x_last']:5.1f} decay={decay:+.4f} A3A4={a3a4:4.1f}% P={rec['p_last']:6.1f}")
            except Exception as e:
                print(f"b{b:>3d} kvac={kvac:.3f} FAIL {e}")
    with open("runs/p3/r130g_kvac_sweep.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print("Saved: runs/p3/r130g_kvac_sweep.json")


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""R130m: 7 批晚期衰亡参数完整扫描（使用完整 COMBINED dict 参数）。

对 7 批未启用晚期衰亡的批次（b27/36/55/60/80/91/92），
使用完整 COMBINED dict 参数 + 不同 late_death 组合，
寻找 yield 在 ±5% 内且 X_offline 衰减改善的参数。

用法：python r130m_late_death_full_scan.py
"""
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from simulate import simulate_open_loop, yield_metrics, classify_crash  # noqa: E402

# 7 批的完整 COMBINED dict 参数
BATCHES = {
    27: {"mux": 0.36, "mup": 0.040, "dist_tcin_asym": 15, "m_s": 0.029,
          "m_s_schedule": [(140, 0.018)], "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85,
          "vis_scale": 0.9, "PAA_c": 530000.0, "m_paa": 1.0, "Y_O2_X": 650, "Y_O2_P": 160, "m_O2_X": 15},
    36: {"mux": 0.47, "mup": 0.045, "dist_tcin_asym": 10, "m_s": 0.010,
          "q_co2": 0.10, "Y_NX": 20, "Y_NP": 40, "alpha_kla": 130},
    55: {"mux": 0.47, "mup": 0.055, "dist_tcin_asym": 20, "m_s": 0.025,
          "biomass_death_rate": 0.001, "death_start": 200,
          "q_co2": 0.11, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},
    60: {"mux": 0.47, "mup": 0.035, "dist_tcin_asym": 15, "m_s": 0.010,
          "q_co2": 0.10, "Y_NX": 20, "Y_NP": 40, "alpha_kla": 85},
    80: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 18, "m_s": 0.029,
          "biomass_death_rate": 0.005, "death_start": 0,
          "q_co2": 0.13, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},
    91: {"mux": 0.40, "mup": 0.040, "dist_tcin_asym": 10, "m_s": 0.029,
          "biomass_death_rate": 0.005, "death_start": 200,
          "q_co2": 0.12, "Y_NX": 10, "Y_NP": 60, "alpha_kla": 90},
    92: {"mux": 0.47, "mup": 0.041, "dist_tcin_asym": 18, "m_s": 0.029,
          "m_s_schedule": [(150, 0.015)], "biomass_death_rate": 0.005, "death_start": 200,
          "q_co2": 0.11, "Y_NX": 12, "Y_NP": 60, "alpha_kla": 130},
}

# 扫描空间（更宽，更低阈值）
MDR_LIST = [0.005, 0.01, 0.02]
DR_LIST = [0.0, 0.1, 0.2, 0.3]
LDR_LIST = [0.002, 0.003, 0.005]


def main():
    out = {"results": []}
    for b, base in BATCHES.items():
        v3 = pd.read_csv(f"data/processed/batches/batch_{b:02d}.csv")
        params0 = {**base, "dist_flag": 1}
        sim0, _ = simulate_open_loop(b, params=params0)
        ym0 = yield_metrics(sim0, v3)
        base_err = ym0["rel_err_total"]
        x0 = sim0["X"].to_numpy(float)
        print(f"b{b:>3d} base yield={base_err:+7.2%} Xpk={x0.max():.1f} Xlast={x0[-1]:.1f}")

        best = {"yield_err": base_err, "x_decay": 0.0}
        for ldr in LDR_LIST:
            for mdr in MDR_LIST:
                for dr in DR_LIST:
                    params = {**base, "dist_flag": 1,
                              "late_death_rate": ldr, "mu_death_ref": mdr,
                              "death_recycle": dr}
                    try:
                        sim, _ = simulate_open_loop(b, params=params)
                        ym = yield_metrics(sim, v3)
                        err = ym["rel_err_total"]
                        level, _ = classify_crash(sim, yield_err=err)
                        x = sim["X"].to_numpy(float)
                        decay = x0[-1] - x[-1]  # 更多衰减 = 更大正值
                        if abs(err) <= 0.05 and level == "normal":
                            flag = "*"
                            if decay > best["x_decay"]:
                                best = {"yield_err": err, "x_decay": decay,
                                        "late_death_rate": ldr, "mu_death_ref": mdr,
                                        "death_recycle": dr, "crash": level,
                                        "Xpk": round(float(x.max()), 1), "Xlast": round(float(x[-1]), 1)}
                                print(f"  ldr={ldr:.3f} mdr={mdr:.3f} dr={dr:.1f} " + flag + f" yield={err:+7.2%} Xlast={x[-1]:.1f} decay={decay:.2f}")
                    except Exception:
                        pass

        out["results"].append({"batch": b, "base_yield_err": round(base_err, 4), **best})
        print(f"  BEST: yield={best['yield_err']:+7.2%} decay={best['x_decay']:.2f}")
        print()

    with open("runs/p3/r130m_late_death_full_scan.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print("Saved: runs/p3/r130m_late_death_full_scan.json")


if __name__ == "__main__":
    main()

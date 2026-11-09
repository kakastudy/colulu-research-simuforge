# -*- coding: utf-8 -*-
"""R130l: 7 批未启用晚期衰亡批次的参数修复尝试。

对 7 批失败批次（b27/36/55/60/80/91/92），尝试不同 mu_death_ref 和
death_recycle 组合，寻找 yield 在 ±5% 内的参数。

用法：python r130l_late_death_fix_attempt.py
"""
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from simulate import simulate_open_loop, yield_metrics, classify_crash  # noqa: E402

# 7 批失败批次及其当前参数
BATCHES = {
    27: {"mux": 0.36, "mup": 0.040, "dist_tcin_asym": 15, "m_s": 0.029,
          "m_s_schedule": [(140, 0.018)], "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},
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

# 扫描空间
MDR_LIST = [0.005, 0.01, 0.02, 0.03]
DR_LIST = [0.0, 0.1, 0.2, 0.3, 0.5]
LDR_LIST = [0.002, 0.003, 0.005, 0.008]


def main():
    out = {"results": []}
    for b, base in BATCHES.items():
        v3 = pd.read_csv(f"data/processed/batches/batch_{b:02d}.csv")
        # 基线
        params0 = {**base, "dist_flag": 1}
        sim0, _ = simulate_open_loop(b, params=params0)
        ym0 = yield_metrics(sim0, v3)
        base_err = ym0["rel_err_total"]
        print(f"b{b:>3d} base yield={base_err:+7.2%}")

        best = {"yield_err": base_err}
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
                        if abs(err) < abs(best["yield_err"]):
                            best = {"yield_err": err, "late_death_rate": ldr,
                                    "mu_death_ref": mdr, "death_recycle": dr,
                                    "crash": level}
                            flag = "*" if abs(err) <= 0.05 and level == "normal" else ""
                            print(f"  ldr={ldr:.3f} mdr={mdr:.3f} dr={dr:.1f} " + flag + f" yield={err:+7.2%} crash={level}")
                    except Exception:
                        pass

        out["results"].append({"batch": b, "base_yield_err": round(base_err, 4), **best})
        flag = "FIXED!" if abs(best["yield_err"]) <= 0.05 else "still-bad"
        print(f"  BEST: yield={best['yield_err']:+7.2%} {flag}")
        print()

    with open("runs/p3/r130l_late_death_fix_attempt.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print("Saved: runs/p3/r130l_late_death_fix_attempt.json")


if __name__ == "__main__":
    main()

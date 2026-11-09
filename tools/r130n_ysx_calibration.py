# -*- coding: utf-8 -*-
"""R130n: Y_sX 逐批校准诊断 —— 减少生物量产量降低 X_offline 幅度。

物理依据：Y_sX（生物量底物产量）控制底物→生物量的转化效率。
降低 Y_sX → 更少底物用于生物量生长 → X_offline 幅度下降 →
更多底物用于青霉素合成 → 产量可能上升。

对 10 批 X_offline nRMSE 最高的黄金批，扫描 Y_sX ∈ [1.2, 1.85]，
寻找 yield 在 ±5% 内且 X_offline 幅度改善的参数。

用法：python r130n_ysx_calibration.py
"""
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from simulate import simulate_open_loop, yield_metrics, classify_crash  # noqa: E402

# 10 批 X_offline nRMSE 最高的黄金批（从 D6 健康视图推断）
# 选取有代表性的批次：高 X_offline nRMSE + 不同参数类型
BATCHES = {
    # 高 X 幅度批（sim Xpk >> V3 Xpk）
    1: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
        "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85, "dist_flag": 1},
    2: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
        "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85, "dist_flag": 1},
    7: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
        "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85, "dist_flag": 1},
    14: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
         "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85, "dist_flag": 1},
    20: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
         "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85, "dist_flag": 1},
    24: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
         "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85, "dist_flag": 1},
    34: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
         "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85, "dist_flag": 1},
    47: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
         "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85, "dist_flag": 1},
    76: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
         "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85, "dist_flag": 1},
    85: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
         "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85, "dist_flag": 1},
}

# 扫描空间
Y_SX_LIST = [1.2, 1.4, 1.5, 1.6, 1.7, 1.85]


def main():
    out = {"results": []}
    for b, base in BATCHES.items():
        v3 = pd.read_csv(f"data/processed/batches/batch_{b:02d}.csv")
        # 基线
        sim0, _ = simulate_open_loop(b, params=dict(base))
        ym0 = yield_metrics(sim0, v3)
        base_err = ym0["rel_err_total"]
        x0 = sim0["X"].to_numpy(float)
        xpk0 = x0.max()
        print(f"b{b:>3d} base yield={base_err:+7.2%} Xpk={xpk0:.1f}")

        best = {"yield_err": base_err, "xpk": xpk0}
        for ysx in Y_SX_LIST:
            params = {**base, "Y_sX": ysx}
            try:
                sim, _ = simulate_open_loop(b, params=params)
                ym = yield_metrics(sim, v3)
                err = ym["rel_err_total"]
                level, _ = classify_crash(sim, yield_err=err)
                x = sim["X"].to_numpy(float)
                xpk = x.max()
                if abs(err) <= 0.05 and level == "normal":
                    flag = "*"
                    if xpk < best["xpk"]:
                        best = {"yield_err": err, "xpk": xpk, "Y_sX": ysx,
                                "crash": level, "Xpk": round(float(xpk), 1)}
                        print(f"  Y_sX={ysx} " + flag + f" yield={err:+7.2%} Xpk={xpk:.1f} (Δ={xpk0-xpk:.1f})")
            except Exception:
                pass

        out["results"].append({"batch": b, "base_yield_err": round(base_err, 4),
                               "base_xpk": round(float(xpk0), 1), **best})
        print(f"  BEST: yield={best['yield_err']:+7.2%} Xpk={best['xpk']:.1f} Y_sX={best.get('Y_sX', 'N/A')}")
        print()

    with open("runs/p3/r130n_ysx_calibration.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print("Saved: runs/p3/r130n_ysx_calibration.json")


if __name__ == "__main__":
    main()

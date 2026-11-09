# -*- coding: utf-8 -*-
"""R130k: 不可修复批根因诊断 + 修复尝试。

对 15 批不可修复批次：
1. 先用名义参数跑仿真，记录 yield_err
2. 尝试 mu_h_scale × mup × Y_NP × m_s 组合
3. 输出每批最佳结果

用法：python r130k_unfixable_diag.py
"""
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from simulate import simulate_open_loop, yield_metrics  # noqa: E402

UNFIXABLE = [4, 6, 10, 13, 19, 21, 25, 32, 44, 51, 81, 94, 97, 99, 100]

# 名义参数
NOMINAL = {"mux": 0.41, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
           "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85,
           "dist_flag": 1}

# 扫描空间
MU_H_SCALES = [0.5, 0.7, 1.0, 1.2, 1.5, 1.8, 2.0, 2.5, 3.0]
MUPS = [0.041, 0.05, 0.06, 0.07, 0.08]
Y_NPS = [40, 50, 60, 80]
M_S_LIST = [0.020, 0.029, 0.035]


def main():
    out = {"results": []}
    for b in UNFIXABLE:
        v3 = pd.read_csv(f"data/processed/batches/batch_{b:02d}.csv")
        # 基线
        sim0, _ = simulate_open_loop(b, params=dict(NOMINAL))
        ym0 = yield_metrics(sim0, v3)
        base_err = ym0["rel_err_total"]
        print(f"b{b:>3d} base yield={base_err:+7.2%}")

        best = {"yield_err": base_err}
        # 扫描 mu_h_scale
        for mh in MU_H_SCALES:
            params = {**NOMINAL, "mu_h_scale": mh}
            try:
                sim, _ = simulate_open_loop(b, params=params)
                ym = yield_metrics(sim, v3)
                err = ym["rel_err_total"]
                if abs(err) < abs(best["yield_err"]):
                    best = {"yield_err": err, "mu_h_scale": mh}
                    print(f"  mh={mh:.1f} yield={err:+7.2%} (best)")
            except Exception:
                pass
        # 扫描 mup
        for mu in MUPS:
            params = {**NOMINAL, "mup": mu}
            try:
                sim, _ = simulate_open_loop(b, params=params)
                ym = yield_metrics(sim, v3)
                err = ym["rel_err_total"]
                if abs(err) < abs(best["yield_err"]):
                    best = {"yield_err": err, "mup": mu}
                    print(f"  mup={mu:.3f} yield={err:+7.2%} (best)")
            except Exception:
                pass
        # 扫描 Y_NP
        for yn in Y_NPS:
            params = {**NOMINAL, "Y_NP": yn}
            try:
                sim, _ = simulate_open_loop(b, params=params)
                ym = yield_metrics(sim, v3)
                err = ym["rel_err_total"]
                if abs(err) < abs(best["yield_err"]):
                    best = {"yield_err": err, "Y_NP": yn}
                    print(f"  Y_NP={yn} yield={err:+7.2%} (best)")
            except Exception:
                pass
        # 扫描 m_s
        for ms in M_S_LIST:
            params = {**NOMINAL, "m_s": ms}
            try:
                sim, _ = simulate_open_loop(b, params=params)
                ym = yield_metrics(sim, v3)
                err = ym["rel_err_total"]
                if abs(err) < abs(best["yield_err"]):
                    best = {"yield_err": err, "m_s": ms}
                    print(f"  m_s={ms:.3f} yield={err:+7.2%} (best)")
            except Exception:
                pass

        out["results"].append({"batch": b, "base_yield_err": round(base_err, 4), **best})
        flag = "FIXED!" if abs(best["yield_err"]) <= 0.05 else "still-bad"
        print(f"  BEST: {best} {flag}")
        print()

    with open("runs/p3/r130k_unfixable_diag.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print("Saved: runs/p3/r130k_unfixable_diag.json")


if __name__ == "__main__":
    main()

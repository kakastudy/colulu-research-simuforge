# -*- coding: utf-8 -*-
"""R130o: 高 mu_death_ref 早期衰亡降低 X_offline 峰值测试。

物理假设：若 mu_death_ref 设得更高（如 0.05-0.1 h⁻¹），晚期衰亡会在
μ_actual 刚下降时即启动，从而削减生物量峰值而非仅尾部。
风险：过早衰亡可能干扰生产相门控 → 产量崩塌（参考 R130g 液泡化教训）。

对 D6 X_offline nRMSE 最高的 15 批黄金批，用其实际 COMBINED 参数 +
late_death 组合扫描（含高 mu_death_ref），检验产量与峰值双指标。

用法：python r130o_early_death_peak_test.py
"""
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from simulate import simulate_open_loop, yield_metrics, classify_crash  # noqa: E402

# 从 diag_final_validation_v3.py 导入 COMBINED dict
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))
import importlib.util
_spec = importlib.util.spec_from_file_location(
    "dfv3", os.path.join(os.path.dirname(__file__), "diag_final_validation_v3.py"))
_dfv3 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_dfv3)
COMBINED = _dfv3.COMBINED

# D6 X_offline nRMSE 最高 15 批
WORST_XOFF = [29, 87, 56, 20, 78, 39, 30, 83, 49, 14, 60, 46, 33, 88, 2]

# 扫描空间：高 mu_death_ref 早期激活
LDR_LIST = [0.003, 0.005, 0.008, 0.012]
MDR_LIST = [0.02, 0.05, 0.08, 0.12]   # 高阈值 = 早期衰亡
DR_LIST = [0.0, 0.3]


def build_params(b):
    cp = COMBINED[b]
    params = {"mux": cp["mux"], "mup": cp["mup"], "alpha_kla": cp.get("alpha_kla", 85.0),
              "PAA_c": cp.get("PAA_c", 530000.0), "N_conc_paa": 150000.0, "c_oil": 1000.0,
              "dist_flag": 1, "dist_tcin_asym": cp["dist_tcin_asym"], "m_s": cp["m_s"]}
    for k in ("m_s_schedule", "biomass_death_rate", "death_start", "q_co2", "Y_NX",
              "Y_NP", "vis_scale", "m_paa", "Y_O2_X", "Y_O2_P", "m_O2_X", "mu_h_scale"):
        if k in cp:
            params[k] = cp[k]
    return params


def main():
    out = {"results": []}
    for b in WORST_XOFF:
        v3 = pd.read_csv(f"data/processed/batches/batch_{b:02d}.csv")
        base = build_params(b)
        sim0, _ = simulate_open_loop(b, params=dict(base))
        ym0 = yield_metrics(sim0, v3)
        base_err = ym0["rel_err_total"]
        x0 = sim0["X"].to_numpy(float)
        lab_x = pd.to_numeric(v3["X_offline"], errors="coerce")
        lab_mean = float(lab_x.mean())
        print(f"b{b:>3d} base yield={base_err:+7.2%} Xpk={x0.max():.1f} labmean={lab_mean:.1f}")

        best = {"yield_err": base_err, "xpk": float(x0.max()), "peak_reduction": 0.0}
        for ldr in LDR_LIST:
            for mdr in MDR_LIST:
                for dr in DR_LIST:
                    params = {**base, "late_death_rate": ldr, "mu_death_ref": mdr,
                              "death_recycle": dr}
                    try:
                        sim, _ = simulate_open_loop(b, params=params)
                        ym = yield_metrics(sim, v3)
                        err = ym["rel_err_total"]
                        level, _ = classify_crash(sim, yield_err=err)
                        x = sim["X"].to_numpy(float)
                        peak_red = float(x0.max() - x.max())
                        if abs(err) <= 0.05 and level == "normal" and peak_red > best["peak_reduction"]:
                            best = {"yield_err": err, "xpk": float(x.max()),
                                    "peak_reduction": peak_red,
                                    "late_death_rate": ldr, "mu_death_ref": mdr,
                                    "death_recycle": dr, "crash": level}
                            print(f"  ldr={ldr:.3f} mdr={mdr:.3f} dr={dr:.1f} * "
                                  f"yield={err:+7.2%} Xpk={x.max():.1f} red={peak_red:.1f}")
                    except Exception:
                        pass

        out["results"].append({"batch": b, "base_yield_err": round(base_err, 4),
                               "base_xpk": round(float(x0.max()), 1), **best})
        print(f"  BEST: yield={best['yield_err']:+7.2%} Xpk={best['xpk']:.1f} "
              f"peak_reduction={best['peak_reduction']:.1f}")
        print()

    with open("runs/p3/r130o_early_death_peak_test.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print("Saved: runs/p3/r130o_early_death_peak_test.json")


if __name__ == "__main__":
    main()

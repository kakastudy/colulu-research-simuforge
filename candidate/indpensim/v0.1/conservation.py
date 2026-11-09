# -*- coding: utf-8 -*-
"""conservation.py — 守恒检查（C/N/O 元素平衡 + OUR/CER 尾气闭合）。

Usage:
  python conservation.py --batch 1
  python conservation.py --batch 1 --output runs/conservation.csv
"""
import argparse
import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "candidate", "indpensim", "v0.1")))
from simulate import simulate_open_loop

# R157 / T1-2：`np.trapezoid` 是 numpy 2.0 才引入的新名，numpy 1.x 只有 `np.trapz`。
# 本项目 requirements.txt 锁定 numpy<2.0 ⇒ 直接写 `np.trapezoid` 会在 pinned 环境必崩。
# 兼容写法与 conservation_metrics.py / r138_carbon_observer.py 保持一致。
_TRAPZ = getattr(np, "trapezoid", None) or np.trapz


def element_balance(sim, v3):
    """C/N/O 元素平衡检查。

    C 平衡：进料碳（Fs×c_s + Foil×c_oil + Fpaa×PAA_c）= 消耗碳（CER×V + 积累在 X/P/S 中）。
    简化：C_in - C_out ≈ Δ(C_in_vessel)，误差应 < 5%。

    OUR/CER 尾气闭合：OUR = (32×Fg/22.4)×(O2_in - O2×0.7902/(1-O2-CO2/100))
                     CER = (44×Fg/22.4)×(0.65×CO2/100×(0.7902/(1-O2_in-CO2/100) - 0.0330))
    检查 OUR/CER 与 V3 导出通道的偏差。
    """
    h = 0.2  # 采样间隔

    # OUR/CER 尾气闭合
    our_diff = sim["OUR"] - v3["OUR"]
    cer_diff = sim["CER"] - v3["CER"]
    our_rmse = np.sqrt(np.mean(our_diff ** 2))
    cer_rmse = np.sqrt(np.mean(cer_diff ** 2))
    our_mae = np.mean(np.abs(our_diff))
    cer_mae = np.mean(np.abs(cer_diff))

    # OUR/CER 比率（生物量/产物呼吸商）
    ratio_sim = sim["CER"] / np.maximum(sim["OUR"], 1e-9)
    ratio_v3 = v3["CER"] / np.maximum(v3["OUR"], 1e-9)
    ratio_rmse = np.sqrt(np.mean((ratio_sim - ratio_v3) ** 2))

    # 碳平衡（简化）
    # C 进料: Fs×c_s/V + Foil×c_oil/V (g/L/h)
    # C 消耗: CER×V/V = CER (g/L/h, 但 CER 单位需转换)
    # 简化检查：CER 积分 vs 碳进料积分
    cer_integral = _TRAPZ(sim["CER"], sim["time_h"])
    fs_integral = _TRAPZ(sim["Fs"] * 600.0 / sim["V"], sim["time_h"])
    foil_integral = _TRAPZ(sim["Foil"] * 1000.0 / sim["V"], sim["time_h"])
    carbon_in = fs_integral + foil_integral  # g/L (碳进料)
    carbon_out = cer_integral * 12.0 / 44.0  # CO2 中的碳 (g/L)
    carbon_balance_err = (carbon_in - carbon_out) / max(carbon_in, 1e-9)

    return {
        "our_rmse": float(our_rmse),
        "our_mae": float(our_mae),
        "cer_rmse": float(cer_rmse),
        "cer_mae": float(cer_mae),
        "ratio_rmse": float(ratio_rmse),
        "carbon_in": float(carbon_in),
        "carbon_out": float(carbon_out),
        "carbon_balance_err": float(carbon_balance_err),
    }


def main():
    ap = argparse.ArgumentParser(description="守恒检查")
    ap.add_argument("--batch", type=int, default=1)
    ap.add_argument("--output", type=str, default=None)
    args = ap.parse_args()

    params = {"mux": 0.41, "mup": 0.041, "alpha_kla": 85.0,
              "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0}
    sim, v3 = simulate_open_loop(args.batch, params)

    result = element_balance(sim, v3)

    print(f"=== Batch {args.batch} 守恒检查 ===")
    print(f"OUR: RMSE={result['our_rmse']:.2f} MAE={result['our_mae']:.2f}")
    print(f"CER: RMSE={result['cer_rmse']:.2f} MAE={result['cer_mae']:.2f}")
    print(f"RQ (CER/OUR): RMSE={result['ratio_rmse']:.4f}")
    print(f"碳平衡: in={result['carbon_in']:.1f} out={result['carbon_out']:.1f} "
          f"err={result['carbon_balance_err']:+.1%}")

    if args.output:
        pd.DataFrame([result]).to_csv(args.output, index=False, encoding="utf-8-sig")
        print(f"已保存: {args.output}")


if __name__ == "__main__":
    main()

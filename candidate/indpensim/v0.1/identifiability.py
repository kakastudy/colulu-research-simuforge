# -*- coding: utf-8 -*-
"""identifiability.py — 参数可辨识性分析（M1）。

对每个批次级参数施加 ±10% 扰动，计算各可观测量的 RMSE 变化。
高灵敏度 + 低相关性 = 可辨识；低灵敏度或高相关性 = 不可辨识。

Usage:
  python identifiability.py --batch 1
"""
import argparse
import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "candidate", "indpensim", "v0.1")))
from simulate import simulate_open_loop

# 批次级参数（名称 → (params_key, par_index, nominal_value)）
BATCH_PARAMS = {
    "mux":        ("mux",        None,  0.41),
    "mup":        ("mup",        None,  0.041),
    "alpha_kla":  ("alpha_kla",  None,  85.0),
    "PAA_c":      ("PAA_c",      None,  530000.0),
    "N_conc_paa": ("N_conc_paa", None,  150000.0),
    "c_oil":      ("c_oil",      None,  1000.0),
    "Tcin":       ("Tcin",       None,  285.0),
}

# 可观测量
OBSERVABLES = ["S", "DO2", "P", "CO2outgas", "OUR", "CER", "pH", "T"]


def sensitivity_analysis(batch_no, perturb=0.10):
    """计算每个批次级参数对各可观测量的灵敏度。"""
    base_params = {"mux": 0.41, "mup": 0.041, "alpha_kla": 85.0,
                   "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0}

    # Baseline
    sim0, _ = simulate_open_loop(batch_no, base_params)

    results = {}
    for pname, (key, idx, nominal) in BATCH_PARAMS.items():
        # +10%
        params_plus = dict(base_params)
        params_plus[key] = nominal * (1.0 + perturb)
        sim_plus, _ = simulate_open_loop(batch_no, params_plus)

        # -10%
        params_minus = dict(base_params)
        params_minus[key] = nominal * (1.0 - perturb)
        sim_minus, _ = simulate_open_loop(batch_no, params_minus)

        # Compute RMSE of each observable
        rmse = {}
        for obs in OBSERVABLES:
            if obs not in sim0.columns or obs not in sim_plus.columns:
                continue
            diff_plus = sim_plus[obs].to_numpy(float) - sim0[obs].to_numpy(float)
            diff_minus = sim0[obs].to_numpy(float) - sim_minus[obs].to_numpy(float)
            rmse[obs] = float(np.sqrt(np.mean(diff_plus ** 2)))
            rmse[obs + "_minus"] = float(np.sqrt(np.mean(diff_minus ** 2)))
        results[pname] = rmse

    return results


def print_sensitivity(results):
    """打印灵敏度矩阵。"""
    params = list(results.keys())
    observables = ["S", "DO2", "P", "CO2outgas", "OUR", "CER", "pH", "T"]

    print(f"{'Param':>12s}", end="")
    for obs in observables:
        print(f" {obs:>10s}", end="")
    print()
    print("-" * (12 + 11 * len(observables)))

    for p in params:
        print(f"{p:>12s}", end="")
        for obs in observables:
            val = results[p].get(obs, float("nan"))
            if val < 0.01:
                print(f" {'—':>10s}", end="")
            else:
                print(f" {val:>10.3f}", end="")
        print()


def main():
    ap = argparse.ArgumentParser(description="参数可辨识性分析")
    ap.add_argument("--batch", type=int, default=1)
    args = ap.parse_args()

    print(f"=== Batch {args.batch} 参数可辨识性分析（±10% 扰动）===\n")
    results = sensitivity_analysis(args.batch)
    print_sensitivity(results)

    # Summary: which params are most/least identifiable
    print("\n=== 可辨识性总结 ===")
    for pname in results:
        total_sens = sum(v for k, v in results[pname].items() if not k.endswith("_minus"))
        print(f"{pname:>12s}: 总灵敏度={total_sens:.3f}")


if __name__ == "__main__":
    main()

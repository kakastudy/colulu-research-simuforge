# -*- coding: utf-8 -*-
"""R129t2: DL σ̂ 替代方案——用黄金回归 COMBINED 值作为批均值估计 σ_pop。

网格后验的批均值过于相似（var_b << var_w → σ_pop=0）。
黄金回归 COMBINED dict 有逐批校准值，var_b 更大。
σ̂²_pop = var(COMBINED_b) − mean(var_w_grid)
"""
import json
import os
import sys

sys.path.insert(0, 'candidate/indpensim/v0.1')
import numpy as np
import hier_est as he


COMBINED = {
    8:  {"mux": 0.47, "mup": 0.041, "m_s": 0.029},
    11: {"mux": 0.41, "mup": 0.041, "m_s": 0.020},
    16: {"mux": 0.41, "mup": 0.041, "m_s": 0.025},
    22: {"mux": 0.35, "mup": 0.065, "m_s": 0.029},
    23: {"mux": 0.35, "mup": 0.070, "m_s": 0.029},
    27: {"mux": 0.35, "mup": 0.041, "m_s": 0.029},
    36: {"mux": 0.47, "mup": 0.045, "m_s": 0.010},
    55: {"mux": 0.47, "mup": 0.055, "m_s": 0.025},
    60: {"mux": 0.47, "mup": 0.035, "m_s": 0.010},
    80: {"mux": 0.35, "mup": 0.041, "m_s": 0.029},
    91: {"mux": 0.39, "mup": 0.041, "m_s": 0.029},
    92: {"mux": 0.47, "mup": 0.041, "m_s": 0.029},
}


def main():
    print("=" * 80, flush=True)
    print("R129t2: DL σ̂ 替代方案——COMBINED 值作为批均值", flush=True)
    print("=" * 80, flush=True)

    # Load grid posterior for var_w
    v2 = he._iter_log(he.PROTOCOLS['v2'][1])
    print(f"Grid posterior: {len(v2)} 批\n", flush=True)

    for param in ("mux", "mup", "m_s"):
        # Compute var_b from COMBINED dict
        combined_vals = np.array([COMBINED[b][param] for b in sorted(COMBINED.keys())])
        var_b_combined = float(np.var(combined_vals, ddof=1))

        # Compute var_w from grid posterior (at T=0.1 for sharp posterior)
        he.T_EB = 0.1
        th_vars = []
        for r in v2:
            sw = [c for c in (r.get("sweep") or []) if c["loss"] < 9e5]
            if len(sw) < 2:
                continue
            arr = np.array([c["loss"] for c in sw])
            w = np.exp(-(arr - arr.min()) / 0.1)
            w /= w.sum()
            vals = np.array([c[param] for c in sw])
            th_vars.append(float(w @ (vals - w @ vals) ** 2))
        var_w_mean = float(np.mean(th_vars))

        # DL estimate with COMBINED as batch means
        var_pop = var_b_combined - var_w_mean
        sigma_pop = float(np.sqrt(max(var_pop, 0.0)))

        # Also compute with grid posterior as batch means
        th_means = []
        for r in v2:
            sw = [c for c in (r.get("sweep") or []) if c["loss"] < 9e5]
            if len(sw) < 2:
                continue
            arr = np.array([c["loss"] for c in sw])
            w = np.exp(-(arr - arr.min()) / 0.1)
            w /= w.sum()
            vals = np.array([c[param] for c in sw])
            th_means.append(float(w @ vals))
        th_means = np.array(th_means)
        var_b_grid = float(np.var(th_means, ddof=1))
        var_pop_grid = var_b_grid - var_w_mean
        sigma_pop_grid = float(np.sqrt(max(var_pop_grid, 0.0)))

        # MATLAB reference
        matlab_ref = {"mux": 0.025, "mup": 0.0025, "m_s": None}

        print(f"  {param}:", flush=True)
        print(f"    COMBINED:  var_b={var_b_combined:.7f} var_w={var_w_mean:.7f} "
              f"σ_pop={sigma_pop:.5f}", flush=True)
        print(f"    Grid:      var_b={var_b_grid:.7f} var_w={var_w_mean:.7f} "
              f"σ_pop={sigma_pop_grid:.5f}", flush=True)
        if matlab_ref[param] is not None:
            print(f"    MATLAB ref: σ={matlab_ref[param]}", flush=True)
        print(flush=True)

    he.T_EB = 1.0


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""R129p2: Q 通道逐时刻相关性分析——识别 V3 Q 代表什么。

V3 Q 与 sim Q 均值比非恒定（0.02-0.28），Qcon/V3 也非恒定（114-1237）。
逐时刻相关性分析可识别 V3 Q 的物理含义。
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))

import numpy as np
import pandas as pd

from simulate import simulate_open_loop


COMBINED = {
    8:  {"mux": 0.47, "mup": 0.041, "dist_tcin_asym": 10, "m_s": 0.029,
          "biomass_death_rate": 0.001, "death_start": 100},
}


def main():
    print("=" * 80, flush=True)
    print("R129p2: Q 通道逐时刻相关性分析", flush=True)
    print("=" * 80, flush=True)

    b = 8
    v3 = pd.read_csv(f"data/processed/batches/batch_{b:02d}.csv")
    cp = COMBINED[b]
    params = {"mux": cp["mux"], "mup": cp["mup"], "alpha_kla": 85.0,
              "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0,
              "dist_flag": 1, "dist_tcin_asym": cp["dist_tcin_asym"], "m_s": cp["m_s"],
              "biomass_death_rate": cp["biomass_death_rate"], "death_start": cp["death_start"]}
    sim, _ = simulate_open_loop(b, params)

    n = min(len(v3), len(sim))
    v3_q = v3['Q'].to_numpy(float)[:n]

    # Check per-timepoint correlation with all sim columns
    correlations = []
    for col in sim.columns:
        sim_vals = sim[col].to_numpy(float)[:n]
        if np.std(sim_vals) > 1e-10 and np.std(v3_q) > 1e-10:
            corr = np.corrcoef(sim_vals, v3_q)[0, 1]
            if abs(corr) > 0.3:
                correlations.append((abs(corr), corr, col, sim_vals.mean()))

    correlations.sort(reverse=True)
    print("Top correlations with V3 Q (batch 8, per-timepoint):", flush=True)
    for abs_c, corr, col, mean in correlations[:20]:
        print("  col={:15s} corr={:+.4f} mean={:.4f}".format(col, corr, mean), flush=True)

    # Also check V3 input columns
    print("\nTop correlations with V3 input columns:", flush=True)
    for col in v3.columns:
        if col == 'Q':
            continue
        v3_vals = v3[col].to_numpy(float)[:n]
        if np.std(v3_vals) > 1e-10:
            corr = np.corrcoef(v3_vals, v3_q)[0, 1]
            if abs(corr) > 0.5:
                print("  V3 col={:15s} corr={:+.4f} mean={:.4f}".format(col, corr, v3_vals.mean()), flush=True)

    # Check if V3 Q is the derivative of sim Q
    print("\nDerivative check:", flush=True)
    sim_q = sim['Q'].to_numpy(float)[:n]
    dq = np.diff(sim_q)
    v3_q_diff = np.diff(v3_q)
    if len(dq) == len(v3_q_diff) and np.std(dq) > 1e-10 and np.std(v3_q_diff) > 1e-10:
        corr_deriv = np.corrcoef(dq, v3_q_diff)[0, 1]
        print("  corr(dQ_sim, dQ_v3) = {:+.4f}".format(corr_deriv), flush=True)

    # Check if V3 Q is related to T - Tair (temperature difference)
    print("\nTemperature difference check:", flush=True)
    sim_t = sim['T'].to_numpy(float)[:n]
    t_diff = sim_t - 298.15  # Tair ≈ 298.15 K
    if np.std(t_diff) > 1e-10:
        corr_t = np.corrcoef(t_diff, v3_q)[0, 1]
        print("  corr(T-Tair, V3_Q) = {:+.4f}".format(corr_t), flush=True)

    # Check if V3 Q is related to Fc (cooling)
    print("\nCooling flow check:", flush=True)
    v3_fc = v3['Fc'].to_numpy(float)[:n]
    if np.std(v3_fc) > 1e-10:
        corr_fc = np.corrcoef(v3_fc, v3_q)[0, 1]
        print("  corr(Fc, V3_Q) = {:+.4f}".format(corr_fc), flush=True)

    # Check if V3 Q is related to total heat removal
    # Q = Fc * Cp * (T - T_cooling) or similar
    print("\nHeat exchange check:", flush=True)
    v3_fh = v3['Fh'].to_numpy(float)[:n]
    total_flow = v3_fc + v3_fh
    if np.std(total_flow) > 1e-10:
        corr_total = np.corrcoef(total_flow, v3_q)[0, 1]
        print("  corr(Fc+Fh, V3_Q) = {:+.4f}".format(corr_total), flush=True)

    # Check if V3 Q is a filtered version of sim Q
    print("\nFiltered Q check:", flush=True)
    for window in [3, 5, 10]:
        sim_q_filtered = pd.Series(sim_q).rolling(window=window, center=True, min_periods=1).mean().to_numpy()
        if np.std(sim_q_filtered) > 1e-10:
            corr_filt = np.corrcoef(sim_q_filtered[:n], v3_q)[0, 1]
            print("  corr(Q_filtered_w={}, V3_Q) = {:+.4f}".format(window, corr_filt), flush=True)


if __name__ == "__main__":
    main()

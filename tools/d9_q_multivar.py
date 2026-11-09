# -*- coding: utf-8 -*-
"""R129p4: Q 通道多变量回归——V3_Q = a*Fc + b*Fh + c*T + d。

V3 Q 与 Fc+Fh 相关性 +0.72，与 T 相关性 +0.99。
多变量回归识别 V3 Q 的物理含义。
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
    print("R129p4: Q 通道多变量回归", flush=True)
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
    v3_fc = v3['Fc'].to_numpy(float)[:n]
    v3_fh = v3['Fh'].to_numpy(float)[:n]
    v3_t = v3['T'].to_numpy(float)[:n]

    # Multivariate regression: V3_Q = a*Fc + b*Fh + c*T + d
    X = np.column_stack([v3_fc, v3_fh, v3_t, np.ones(n)])
    coeffs, residuals, rank, sv = np.linalg.lstsq(X, v3_q, rcond=None)
    pred = X @ coeffs
    rmse = float(np.sqrt(np.mean((pred - v3_q) ** 2)))
    nrmse = rmse / np.mean(v3_q) * 100 if np.mean(v3_q) > 1e-10 else 0

    print("  V3_Q = {:.6f}*Fc + {:.6f}*Fh + {:.6f}*T + {:.4f}".format(
        coeffs[0], coeffs[1], coeffs[2], coeffs[3]), flush=True)
    print("  RMSE={:.2f} nRMSE={:.1f}%".format(rmse, nrmse), flush=True)

    # Try with sim Q as additional feature
    sim_q = sim['Q'].to_numpy(float)[:n]
    X2 = np.column_stack([v3_fc, v3_fh, v3_t, sim_q, np.ones(n)])
    coeffs2, _, _, _ = np.linalg.lstsq(X2, v3_q, rcond=None)
    pred2 = X2 @ coeffs2
    rmse2 = float(np.sqrt(np.mean((pred2 - v3_q) ** 2)))
    nrmse2 = rmse2 / np.mean(v3_q) * 100 if np.mean(v3_q) > 1e-10 else 0

    print("\n  With sim_Q: V3_Q = {:.6f}*Fc + {:.6f}*Fh + {:.6f}*T + {:.6f}*sim_Q + {:.4f}".format(
        coeffs2[0], coeffs2[1], coeffs2[2], coeffs2[3], coeffs2[4]), flush=True)
    print("  RMSE={:.2f} nRMSE={:.1f}%".format(rmse2, nrmse2), flush=True)

    # Try: V3_Q = a*Fc*(T - Tc) where Tc is estimated
    # Q = U*A*(T - Tc) → Q/(T-Tc) = U*A = constant
    # If V3 Q = Fc * (T - T_cooling), then V3_Q/Fc = T - T_cooling
    # T_cooling = T - V3_Q/Fc
    cooling_out_temp = v3_t - v3_q / np.where(v3_fc > 0, v3_fc, 1e-10)
    print("\n  Estimated cooling outlet temp: min={:.2f} max={:.2f} mean={:.2f}".format(
        cooling_out_temp[v3_fc > 1].min(), cooling_out_temp[v3_fc > 1].max(),
        cooling_out_temp[v3_fc > 1].mean()), flush=True)

    # Try: V3_Q = a*Fc*(T - Tc_in)
    # If Tc_in is constant, then V3_Q/Fc = a*(T - Tc_in)
    # This is linear in T
    valid = v3_fc > 1
    if np.sum(valid) > 10:
        q_over_fc = v3_q[valid] / v3_fc[valid]
        t_valid = v3_t[valid]
        A = np.vstack([t_valid, np.ones(len(t_valid))]).T
        a_tc, b_tc = np.linalg.lstsq(A, q_over_fc, rcond=None)[0]
        pred_q = (a_tc * v3_t + b_tc) * v3_fc
        pred_q[~valid] = 0
        rmse3 = float(np.sqrt(np.mean((pred_q - v3_q) ** 2)))
        nrmse3 = rmse3 / np.mean(v3_q) * 100 if np.mean(v3_q) > 1e-10 else 0
        print("\n  V3_Q = ({:.6f}*T + {:.4f})*Fc → nRMSE={:.1f}%".format(a_tc, b_tc, nrmse3), flush=True)
        print("  → Tc_in = -{:.4f}/{:.6f} = {:.2f} K".format(b_tc, a_tc, -b_tc/a_tc), flush=True)


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""R129p5: 验证 V3 Q 是输入数据的计算量——跨 12 批验证。

多变量回归显示 V3_Q ≈ f(Fc, Fh, T)（nRMSE=1.4%），sim_Q 系数≈0。
V3 Q 不是独立测量，而是输入数据的派生量。
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))

import numpy as np
import pandas as pd


GOLDEN = [8, 11, 16, 22, 23, 27, 36, 55, 60, 80, 91, 92]


def main():
    print("=" * 80, flush=True)
    print("R129p5: V3 Q 计算量验证——跨 12 批", flush=True)
    print("=" * 80, flush=True)

    # Fit regression on batch 8, apply to all batches
    v3_8 = pd.read_csv("data/processed/batches/batch_08.csv")
    n8 = len(v3_8)
    q_8 = v3_8['Q'].to_numpy(float)
    fc_8 = v3_8['Fc'].to_numpy(float)
    fh_8 = v3_8['Fh'].to_numpy(float)
    t_8 = v3_8['T'].to_numpy(float)

    X8 = np.column_stack([fc_8, fh_8, t_8, np.ones(n8)])
    coeffs = np.linalg.lstsq(X8, q_8, rcond=None)[0]
    print("  Regression (from batch 8): V3_Q = {:.6f}*Fc + {:.6f}*Fh + {:.6f}*T + {:.4f}".format(
        coeffs[0], coeffs[1], coeffs[2], coeffs[3]), flush=True)

    print("\n  Validation on all batches:", flush=True)
    for b in GOLDEN:
        v3 = pd.read_csv(f"data/processed/batches/batch_{b:02d}.csv")
        n = len(v3)
        q = v3['Q'].to_numpy(float)
        fc = v3['Fc'].to_numpy(float)
        fh = v3['Fh'].to_numpy(float)
        t = v3['T'].to_numpy(float)

        pred = coeffs[0] * fc + coeffs[1] * fh + coeffs[2] * t + coeffs[3]
        rmse = float(np.sqrt(np.mean((pred - q) ** 2)))
        nrmse = rmse / np.mean(q) * 100 if np.mean(q) > 1e-10 else 0

        # Also check if V3 Q = 0 when Fc=0 and Fh=0 (early batch phase)
        no_flow = (fc < 1) & (fh < 1)
        q_no_flow = q[no_flow].mean() if np.any(no_flow) else float('nan')

        print("  Batch {:2d}: nRMSE={:.1f}% mean_Q={:.1f} mean_Q_no_flow={:.1f}".format(
            b, nrmse, np.mean(q), q_no_flow), flush=True)

    print("\nConclusion:", flush=True)
    print("  V3 Q is a computed quantity from V3 inputs (Fc, Fh, T).", flush=True)
    print("  It should NOT be compared with sim Q (y[8]/1000).", flush=True)
    print("  The Q channel should be removed from D6 health view", flush=True)
    print("  or redefined as a consistency check on V3 inputs.", flush=True)


if __name__ == "__main__":
    main()

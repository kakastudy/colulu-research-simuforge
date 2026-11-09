# -*- coding: utf-8 -*-
"""R129p6: 逐批回归 V3_Q = f(Fc, Fh, T) 验证。"""
import os
import sys

import numpy as np
import pandas as pd


GOLDEN = [8, 11, 16, 22, 23, 27, 36, 55, 60, 80, 91, 92]


def main():
    print("=" * 80, flush=True)
    print("R129p6: 逐批回归 V3_Q = f(Fc, Fh, T)", flush=True)
    print("=" * 80, flush=True)

    for b in GOLDEN:
        v3 = pd.read_csv(f"data/processed/batches/batch_{b:02d}.csv")
        n = len(v3)
        q = v3['Q'].to_numpy(float)
        fc = v3['Fc'].to_numpy(float)
        fh = v3['Fh'].to_numpy(float)
        t = v3['T'].to_numpy(float)

        # Per-batch regression
        X = np.column_stack([fc, fh, t, np.ones(n)])
        coeffs = np.linalg.lstsq(X, q, rcond=None)[0]
        pred = X @ coeffs
        rmse = float(np.sqrt(np.mean((pred - q) ** 2)))
        nrmse = rmse / np.mean(q) * 100 if np.mean(q) > 1e-10 else 0

        # R²
        ss_res = float(np.sum((pred - q) ** 2))
        ss_tot = float(np.sum((q - np.mean(q)) ** 2))
        r2 = 1 - ss_res / ss_tot if ss_tot > 1e-10 else 0

        print("  Batch {:2d}: nRMSE={:.1f}% R²={:.4f} | a={:.6f} b={:.6f} c={:.4f} d={:.2f}".format(
            b, nrmse, r2, coeffs[0], coeffs[1], coeffs[2], coeffs[3]), flush=True)

    print("\nConclusion:", flush=True)
    print("  If R² is high (>0.9) for all batches, V3 Q is", flush=True)
    print("  a computed function of V3 inputs, not a measurement.", flush=True)
    print("  Sim Q (y[8]/1000) is a different physical quantity.", flush=True)
    print("  Q channel should be removed from D6 health view.", flush=True)


if __name__ == "__main__":
    main()

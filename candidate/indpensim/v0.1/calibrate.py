# -*- coding: utf-8 -*-
"""Fix calibration: use time-based filtering instead of boolean indexing."""
import argparse
import json
import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "candidate", "indpensim", "v0.1")))
from simulate import simulate_open_loop, yield_metrics

CO2D_THRESHOLD = 7.57


def rmse_channel(sim, v3, ch, t_lo, t_hi):
    """RMSE of a channel in [t_lo, t_hi] using time-based filtering."""
    s = sim[(sim.time_h >= t_lo) & (sim.time_h <= t_hi)]
    v = v3[(v3.time_h >= t_lo) & (v3.time_h <= t_hi)]
    if len(s) == 0 or len(v) == 0:
        return 1e9
    # Align by time
    n = min(len(s), len(v))
    diff = s.iloc[:n][ch].to_numpy(float) - v.iloc[:n][ch].to_numpy(float)
    return float(np.sqrt(np.mean(diff ** 2)))


def crash_penalty(sim):
    co2d_max = sim["CO2d"].max() if "CO2d" in sim.columns else 0.0
    return max(0.0, (co2d_max - CO2D_THRESHOLD)) ** 2 * 50.0


def calibrate_batch(batch_no, verbose=True):
    v3 = pd.read_csv(f"data/processed/batches/batch_{batch_no:02d}.csv")

    mux = 0.41
    mup = 0.041
    kla = 85.0

    for iteration in range(3):
        # 1. Scan mux → CO2outgas
        best_mux, best_err = mux, 1e9
        for mux_try in np.arange(0.30, 0.50, 0.02):
            params = {"mux": float(mux_try), "mup": mup, "alpha_kla": kla,
                      "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0}
            sim, _ = simulate_open_loop(batch_no, params)
            err = rmse_channel(sim, v3, "CO2outgas", 50, 150) + crash_penalty(sim) * 0.1
            if err < best_err:
                best_err = err
                best_mux = float(mux_try)
        mux = best_mux

        # 2. Scan mup → P
        best_mup, best_err = mup, 1e9
        for mup_try in np.arange(0.030, 0.060, 0.005):
            params = {"mux": mux, "mup": float(mup_try), "alpha_kla": kla,
                      "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0}
            sim, _ = simulate_open_loop(batch_no, params)
            err = rmse_channel(sim, v3, "P", 100, 180) + crash_penalty(sim) * 0.1
            if err < best_err:
                best_err = err
                best_mup = float(mup_try)
        mup = best_mup

        # 3. Scan alpha_kla → DO2
        best_kla, best_err = kla, 1e9
        for kla_try in np.arange(55, 100, 3.0):
            params = {"mux": mux, "mup": mup, "alpha_kla": float(kla_try),
                      "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0}
            sim, _ = simulate_open_loop(batch_no, params)
            err = rmse_channel(sim, v3, "DO2", 50, 150) + crash_penalty(sim) * 0.1
            if err < best_err:
                best_err = err
                best_kla = float(kla_try)
        kla = best_kla

        if verbose:
            print(f"  iter {iteration+1}: mux={mux:.3f} mup={mup:.4f} kla={kla:.1f}")

    # Final validation
    params = {"mux": mux, "mup": mup, "alpha_kla": kla,
              "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0}
    sim, _ = simulate_open_loop(batch_no, params)
    co2d_max = sim["CO2d"].max()
    crashed = co2d_max > CO2D_THRESHOLD
    ym = yield_metrics(sim, v3)

    if verbose:
        print(f"\n  Calibrated: mux={mux:.3f} mup={mup:.4f} kla={kla:.1f}")
        print(f"  CO2 RMSE={rmse_channel(sim,v3,'CO2outgas',50,150):.3f} "
              f"P RMSE={rmse_channel(sim,v3,'P',100,180):.3f} "
              f"DO2 RMSE={rmse_channel(sim,v3,'DO2',50,150):.3f}")
        print(f"  CO2d_max={co2d_max:.2f} {'CRASH' if crashed else 'ok'}")
        print(f"  yield={ym['total_sim_g']:,.0f} (V3={ym['total_v3_g']:,.0f}) err={ym['rel_err_total']:+.1%}")

    return {
        "batch": batch_no, "mux": mux, "mup": mup, "alpha_kla": kla,
        "co2d_max": co2d_max, "crashed": crashed,
        "yield_sim": ym["total_sim_g"], "yield_v3": ym["total_v3_g"],
        "yield_rel_err": ym["rel_err_total"],
    }


def main():
    ap = argparse.ArgumentParser(description="Per-batch calibration")
    ap.add_argument("--batch", type=int, nargs="+", default=[1])
    ap.add_argument("--save", type=str, default=None)
    args = ap.parse_args()

    results = []
    for b in args.batch:
        print(f"\n=== Batch {b} ===")
        r = calibrate_batch(b)
        results.append(r)

    if args.save:
        with open(args.save, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"\n已保存: {args.save}")


if __name__ == "__main__":
    main()

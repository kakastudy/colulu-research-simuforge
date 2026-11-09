# -*- coding: utf-8 -*-
"""R129q: OUR/CER 通道单位与公式验证。"""
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
    print("R129q: OUR/CER 通道单位与公式验证", flush=True)
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

    print("\nV3 values:", flush=True)
    print("  O2:       min={:.4f} max={:.4f} mean={:.4f}".format(
        v3['O2'].min(), v3['O2'].max(), v3['O2'].mean()))
    print("  CO2outgas: min={:.4f} max={:.4f} mean={:.4f}".format(
        v3['CO2outgas'].min(), v3['CO2outgas'].max(), v3['CO2outgas'].mean()))
    print("  OUR:      min={:.4f} max={:.4f} mean={:.4f}".format(
        v3['OUR'].min(), v3['OUR'].max(), v3['OUR'].mean()))
    print("  CER:      min={:.4f} max={:.4f} mean={:.4f}".format(
        v3['CER'].min(), v3['CER'].max(), v3['CER'].mean()))

    print("\nSim values:", flush=True)
    print("  O2:       min={:.4f} max={:.4f} mean={:.4f}".format(
        sim['O2'][:n].min(), sim['O2'][:n].max(), sim['O2'][:n].mean()))
    print("  CO2outgas: min={:.4f} max={:.4f} mean={:.4f}".format(
        sim['CO2outgas'][:n].min(), sim['CO2outgas'][:n].max(), sim['CO2outgas'][:n].mean()))
    print("  OUR:      min={:.4f} max={:.4f} mean={:.4f}".format(
        sim['OUR'][:n].min(), sim['OUR'][:n].max(), sim['OUR'][:n].mean()))
    print("  CER:      min={:.4f} max={:.4f} mean={:.4f}".format(
        sim['CER'][:n].min(), sim['CER'][:n].max(), sim['CER'][:n].mean()))

    # Check OUR/CER ratio
    print("\nOUR/CER ratios:", flush=True)
    print("  V3:  mean={:.4f}".format(np.mean(v3['OUR']) / np.mean(v3['CER'])))
    print("  Sim: mean={:.4f}".format(np.mean(sim['OUR'][:n]) / np.mean(sim['CER'][:n])))

    # Check if OUR + CER ≈ O2 consumption
    print("\nOUR + CER:", flush=True)
    print("  V3:  mean={:.4f}".format(np.mean(v3['OUR'] + v3['CER'])))
    print("  Sim: mean={:.4f}".format(np.mean(sim['OUR'][:n] + sim['CER'][:n])))

    # Manual OUR calculation with correct formula
    # OUR = (32/22.4) * Fg * (0.204 * 0.7902 / (1 - o2 - co2) - o2)
    # vs current: OUR = (32/22.4) * Fg * (0.204 - o2 * 0.7902 / (1 - o2 - co2/100))
    print("\nManual OUR calculation comparison:", flush=True)
    o2_sim = sim['O2'][:n].to_numpy(float)
    co2_sim = sim['CO2outgas'][:n].to_numpy(float)
    fg = v3['Fg'][:n].to_numpy(float)
    o2_v3 = v3['O2'][:n].to_numpy(float)
    co2_v3 = v3['CO2outgas'][:n].to_numpy(float)

    # Current formula (with co2/100)
    our_current = (32.0 * fg / 22.4) * (0.204 - o2_v3 * (0.7902 / (1.0 - o2_v3 - co2_v3 / 100.0)))
    # Alternative formula (co2 as fraction, no /100)
    our_alt = (32.0 * fg / 22.4) * (0.204 * 0.7902 / (1.0 - o2_v3 - co2_v3) - o2_v3)
    # Another alternative
    our_alt2 = (32.0 * fg / 22.4) * (0.204 - o2_v3 * (0.7902 / (1.0 - o2_v3 - co2_v3)))

    print("  Current formula:  mean={:.4f} (V3 mean={:.4f})".format(
        np.mean(our_current), np.mean(v3['OUR'])))
    print("  Alt formula 1:    mean={:.4f}".format(np.mean(our_alt)))
    print("  Alt formula 2:    mean={:.4f}".format(np.mean(our_alt2)))

    # nRMSE for each
    for name, our_calc in [("Current", our_current), ("Alt1", our_alt), ("Alt2", our_alt2)]:
        rmse = float(np.sqrt(np.mean((our_calc - v3['OUR'][:n].to_numpy(float)) ** 2)))
        nrmse = rmse / np.mean(v3['OUR']) * 100 if np.mean(v3['OUR']) > 1e-10 else 0
        print("  {}: nRMSE={:.1f}%".format(name, nrmse))

    # Check CER formula
    cer_current = (44.0 * fg / 22.4) * ((0.65 * co2_v3 / 100.0)
                                       * (0.7902 / (1.0 - 0.204 - co2_v3 / 100.0) - 0.0330))
    print("\n  CER current: mean={:.4f} (V3 mean={:.4f})".format(
        np.mean(cer_current), np.mean(v3['CER'])))


if __name__ == "__main__":
    main()

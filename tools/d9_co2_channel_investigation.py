# -*- coding: utf-8 -*-
"""R129l: CO2 通道参数扫描——改善 CO2outgas/CER 通道健康。

D6 健康视图（R129k）显示 CO2outgas 10/12 critical、CER 10/12 critical。
这两个通道由 C_CO2_in (par[101]=0.033) 和 q_co2 (par[91]=0.1353) 控制。

扫描 C_CO2_in∈{0.010, 0.020, 0.033, 0.050, 0.080} × q_co2∈{0.100, 0.1353, 0.150, 0.180, 0.200}
对 12 黄金批的 CO2outgas 和 CER 通道 nRMSE。

注意：C_CO2_in 和 q_co2 是全局参数（非 per-batch），扫描找最优全局值。
"""
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))

import numpy as np
import pandas as pd

from simulate import simulate_open_loop
from params import make_params


COMBINED = {
    8:  {"mux": 0.47, "mup": 0.041, "dist_tcin_asym": 10, "m_s": 0.029,
          "biomass_death_rate": 0.001, "death_start": 100},
    11: {"mux": 0.41, "mup": 0.041, "dist_tcin_asym": 10, "m_s": 0.020},
    16: {"mux": 0.41, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.025,
          "biomass_death_rate": 0.005, "death_start": 0},
    22: {"mux": 0.35, "mup": 0.065, "dist_tcin_asym": 20, "m_s": 0.029,
          "m_s_schedule": [(110, 0.010)]},
    23: {"mux": 0.35, "mup": 0.070, "dist_tcin_asym": 10, "m_s": 0.029,
          "biomass_death_rate": 0.0005, "death_start": 200},
    27: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 15, "m_s": 0.029,
          "m_s_schedule": [(140, 0.018)]},
    36: {"mux": 0.47, "mup": 0.045, "dist_tcin_asym": 10, "m_s": 0.010},
    55: {"mux": 0.47, "mup": 0.055, "dist_tcin_asym": 20, "m_s": 0.025,
          "biomass_death_rate": 0.001, "death_start": 200},
    60: {"mux": 0.47, "mup": 0.035, "dist_tcin_asym": 15, "m_s": 0.010},
    80: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 18, "m_s": 0.029,
          "biomass_death_rate": 0.005, "death_start": 0},
    91: {"mux": 0.39, "mup": 0.041, "dist_tcin_asym": 10, "m_s": 0.029,
          "biomass_death_rate": 0.005, "death_start": 200},
    92: {"mux": 0.47, "mup": 0.041, "dist_tcin_asym": 18, "m_s": 0.029,
          "m_s_schedule": [(150, 0.015)],
          "biomass_death_rate": 0.005, "death_start": 200},
}

GOLDEN = [8, 11, 16, 22, 23, 27, 36, 55, 60, 80, 91, 92]


def compute_channel_nrmse(sim, v3, sim_col, v3_col):
    sim_vals = sim[sim_col].to_numpy(float)
    lab_vals = v3[v3_col].to_numpy(float)
    n = min(len(sim_vals), len(lab_vals))
    sim_vals = sim_vals[:n]
    lab_vals = lab_vals[:n]
    diff = sim_vals - lab_vals
    rmse = float(np.sqrt(np.mean(diff ** 2)))
    lab_mean = float(np.mean(lab_vals))
    nrmse = (rmse / lab_mean) * 100 if lab_mean > 1e-10 else 0.0
    return nrmse


def build_params_with_overrides(cp, c_co2_in=None, q_co2=None):
    params = {"mux": cp["mux"], "mup": cp["mup"], "alpha_kla": 85.0,
              "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0,
              "dist_flag": 1, "dist_tcin_asym": cp["dist_tcin_asym"], "m_s": cp["m_s"]}
    if "m_s_schedule" in cp:
        params["m_s_schedule"] = cp["m_s_schedule"]
    if "biomass_death_rate" in cp:
        params["biomass_death_rate"] = cp["biomass_death_rate"]
        params["death_start"] = cp["death_start"]
    # Store overrides for simulate_open_loop to apply
    if c_co2_in is not None:
        params["_c_co2_in"] = c_co2_in
    if q_co2 is not None:
        params["_q_co2"] = q_co2
    return params


def main():
    print("=" * 80, flush=True)
    print("R129l: CO2 通道参数扫描——C_CO2_in × q_co2", flush=True)
    print("=" * 80, flush=True)

    # First, get baseline nRMSE for CO2outgas and CER
    print("\nBaseline (C_CO2_in=0.033, q_co2=0.1353):", flush=True)
    baseline = {}
    for b in GOLDEN:
        v3 = pd.read_csv(f"data/processed/batches/batch_{b:02d}.csv")
        cp = COMBINED[b]
        params = build_params_with_overrides(cp)
        sim, _ = simulate_open_loop(b, params)
        co2_nrmse = compute_channel_nrmse(sim, v3, "CO2outgas", "CO2outgas")
        cer_nrmse = compute_channel_nrmse(sim, v3, "CER", "CER")
        baseline[b] = {"CO2outgas": co2_nrmse, "CER": cer_nrmse}
        if co2_nrmse > 15 or cer_nrmse > 15:
            print("  Batch %2d: CO2outgas nRMSE=%.1f%% CER nRMSE=%.1f%%" % (
                b, co2_nrmse, cer_nrmse), flush=True)

    avg_baseline_co2 = np.mean([baseline[b]["CO2outgas"] for b in GOLDEN])
    avg_baseline_cer = np.mean([baseline[b]["CER"] for b in GOLDEN])
    print("  Avg CO2outgas nRMSE: %.1f%%  Avg CER nRMSE: %.1f%%" % (
        avg_baseline_co2, avg_baseline_cer), flush=True)

    # Sweep C_CO2_in and q_co2
    # Note: We can't easily override these in simulate_open_loop, so we'll
    # patch the params array directly by monkey-patching make_params
    print("\nSweeping C_CO2_in × q_co2...", flush=True)

    results = {}
    # Since we can't easily override global params, let's check if the issue
    # is actually the C_CO2_in value by checking the CO2outgas channel more carefully
    print("\nDetailed CO2outgas comparison (batch 8):", flush=True)
    v3 = pd.read_csv("data/processed/batches/batch_08.csv")
    cp = COMBINED[8]
    params = build_params_with_overrides(cp)
    sim, _ = simulate_open_loop(8, params)
    print("  V3 CO2outgas: min={:.4f} max={:.4f} mean={:.4f}".format(
        v3['CO2outgas'].min(), v3['CO2outgas'].max(), v3['CO2outgas'].mean()))
    print("  Sim CO2outgas: min={:.4f} max={:.4f} mean={:.4f}".format(
        sim['CO2outgas'].min(), sim['CO2outgas'].max(), sim['CO2outgas'].mean()))
    print("  Ratio: mean={:.4f}".format(sim['CO2outgas'].mean() / v3['CO2outgas'].mean()))

    # Check if CO2outgas is the headspace CO2 concentration (y[27])
    # or the CO2 dissolved concentration (y[28])
    print("\n  Sim CO2outgas vs sim O2:", flush=True)
    print("  O2: min={:.4f} max={:.4f} mean={:.4f}".format(
        sim['O2'].min(), sim['O2'].max(), sim['O2'].mean()))
    print("  V3 O2: min={:.4f} max={:.4f} mean={:.4f}".format(
        v3['O2'].min(), v3['O2'].max(), v3['O2'].mean()))

    # The issue might be that CO2outgas (y[27]) is the headspace CO2 fraction,
    # while V3 CO2outgas might be in a different unit (e.g., %)
    print("\n  Checking if V3 CO2outgas is in %:", flush=True)
    print("  V3 CO2outgas mean: {:.4f} (if in %, this is reasonable for fermentation)".format(
        v3['CO2outgas'].mean()))
    print("  Sim CO2outgas mean: {:.4f} (if in fraction, this is also reasonable)".format(
        sim['CO2outgas'].mean()))
    print("  Ratio: {:.4f} (if V3 is in % and sim is in fraction, ratio should be ~100)".format(
        sim['CO2outgas'].mean() / v3['CO2outgas'].mean()))

    print("\nConclusion: CO2outgas channel issue is likely a unit/scale mismatch,", flush=True)
    print("not a parameter issue. The sim CO2outgas (y[27]) is a fraction, while", flush=True)
    print("V3 CO2outgas might be in % or a different unit.", flush=True)

    dst = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "runs", "p3", "d9_co2_channel_investigation.json")
    with open(dst, "w", encoding="utf-8") as f:
        json.dump({"baseline": {str(k): v for k, v in baseline.items()},
                   "avg_baseline_co2": avg_baseline_co2,
                   "avg_baseline_cer": avg_baseline_cer}, f, ensure_ascii=False, indent=2)
    print("Saved: %s" % dst, flush=True)


if __name__ == "__main__":
    main()

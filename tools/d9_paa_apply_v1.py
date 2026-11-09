# -*- coding: utf-8 -*-
"""R129af: Apply per-batch PAA_c and m_paa to COMBINED dict.

Strategy: For each batch, compute baseline PAA nRMSE with default params
(PAA_c=530000, m_paa=1.05). If v1 best is better AND yield is safe, apply.
Otherwise keep default. Then run golden regression to verify yield.
"""
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))

import numpy as np
import pandas as pd

from simulate import simulate_open_loop, yield_metrics


COMBINED = {
    8:  {"mux": 0.47, "mup": 0.041, "dist_tcin_asym": 10, "m_s": 0.029,
          "biomass_death_rate": 0.001, "death_start": 100, "q_co2": 0.12, "Y_NX": 10, "Y_NP": 80, "alpha_kla": 90, "vis_scale": 0.9},
    11: {"mux": 0.41, "mup": 0.041, "dist_tcin_asym": 10, "m_s": 0.020, "q_co2": 0.11, "Y_NX": 10, "Y_NP": 80, "alpha_kla": 110, "vis_scale": 0.9},
    16: {"mux": 0.41, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.025,
          "biomass_death_rate": 0.005, "death_start": 0, "q_co2": 0.14, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 75, "vis_scale": 0.9},
    22: {"mux": 0.35, "mup": 0.065, "dist_tcin_asym": 20, "m_s": 0.029,
          "m_s_schedule": [(110, 0.010)], "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},
    23: {"mux": 0.35, "mup": 0.070, "dist_tcin_asym": 10, "m_s": 0.029,
          "biomass_death_rate": 0.0005, "death_start": 200, "q_co2": 0.1, "Y_NX": 15, "Y_NP": 60, "alpha_kla": 110, "vis_scale": 0.9},
    27: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 15, "m_s": 0.029,
          "m_s_schedule": [(140, 0.018)], "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85, "vis_scale": 0.9},
    36: {"mux": 0.47, "mup": 0.045, "dist_tcin_asym": 10, "m_s": 0.010, "q_co2": 0.1, "Y_NX": 20, "Y_NP": 40, "alpha_kla": 130, "vis_scale": 0.8},
    55: {"mux": 0.47, "mup": 0.055, "dist_tcin_asym": 20, "m_s": 0.025,
          "biomass_death_rate": 0.001, "death_start": 200, "q_co2": 0.11, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},
    60: {"mux": 0.47, "mup": 0.035, "dist_tcin_asym": 15, "m_s": 0.010, "q_co2": 0.1, "Y_NX": 20, "Y_NP": 40, "alpha_kla": 85},
    80: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 18, "m_s": 0.029,
          "biomass_death_rate": 0.005, "death_start": 0, "q_co2": 0.13, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85, "vis_scale": 0.9},
    91: {"mux": 0.39, "mup": 0.041, "dist_tcin_asym": 10, "m_s": 0.029,
          "biomass_death_rate": 0.005, "death_start": 200, "q_co2": 0.12, "Y_NX": 10, "Y_NP": 60, "alpha_kla": 90},
    92: {"mux": 0.47, "mup": 0.041, "dist_tcin_asym": 18, "m_s": 0.029,
          "m_s_schedule": [(150, 0.015)],
          "biomass_death_rate": 0.005, "death_start": 200, "q_co2": 0.11, "Y_NX": 12, "Y_NP": 60, "alpha_kla": 130, "vis_scale": 0.9},
}

GOLDEN = [8, 11, 16, 22, 23, 27, 36, 55, 60, 80, 91, 92]

# v1 best results
V1_BEST = {
    8:  {"PAA_c": 530000, "m_paa": 1.0, "paa_nrmse": 8.5, "yield_err": 0.0060},
    11: {"PAA_c": 530000, "m_paa": 0.7, "paa_nrmse": 18.3, "yield_err": 0.0303},
    16: {"PAA_c": 400000, "m_paa": 0.5, "paa_nrmse": 26.0, "yield_err": 0.0041},
    22: {"PAA_c": 530000, "m_paa": 0.5, "paa_nrmse": float('inf'), "yield_err": 0.0},
    23: {"PAA_c": 530000, "m_paa": 1.0, "paa_nrmse": 78.1, "yield_err": 0.0430},
    27: {"PAA_c": 530000, "m_paa": 1.0, "paa_nrmse": 30.2, "yield_err": 0.0444},
    36: {"PAA_c": 530000, "m_paa": 0.7, "paa_nrmse": 19.3, "yield_err": 0.0048},
    55: {"PAA_c": 530000, "m_paa": 1.0, "paa_nrmse": 54.3, "yield_err": -0.0073},
    60: {"PAA_c": 530000, "m_paa": 1.0, "paa_nrmse": 21.9, "yield_err": 0.0179},
    80: {"PAA_c": 400000, "m_paa": 0.3, "paa_nrmse": 23.3, "yield_err": -0.0007},
    91: {"PAA_c": 400000, "m_paa": 0.05, "paa_nrmse": 26.3, "yield_err": -0.0102},
    92: {"PAA_c": 530000, "m_paa": 0.7, "paa_nrmse": 25.8, "yield_err": -0.0189},
}


def build_params(cp, paa_c=None, m_paa=None):
    params = {"mux": cp["mux"], "mup": cp["mup"], "alpha_kla": cp["alpha_kla"],
              "PAA_c": paa_c or 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0,
              "dist_flag": 1, "dist_tcin_asym": cp["dist_tcin_asym"], "m_s": cp["m_s"],
              "q_co2": cp["q_co2"], "Y_NX": cp["Y_NX"], "Y_NP": cp["Y_NP"]}
    if m_paa is not None:
        params["m_paa"] = m_paa
    if "vis_scale" in cp:
        params["vis_scale"] = cp["vis_scale"]
    if "m_s_schedule" in cp:
        params["m_s_schedule"] = cp["m_s_schedule"]
    if "biomass_death_rate" in cp:
        params["biomass_death_rate"] = cp["biomass_death_rate"]
        params["death_start"] = cp["death_start"]
    return params


def compute_channel_nrmse(sim, v3, sim_col, v3_col):
    sim_vals = sim[sim_col].to_numpy(float)
    lab_vals = v3[v3_col].to_numpy(float)
    n = min(len(sim_vals), len(lab_vals))
    sim_vals = sim_vals[:n]
    lab_vals = lab_vals[:n]
    valid = ~np.isnan(lab_vals)
    if not np.any(valid):
        return 0.0
    sim_v = sim_vals[valid]
    lab_v = lab_vals[valid]
    diff = sim_v - lab_v
    rmse = float(np.sqrt(np.mean(diff ** 2)))
    lab_mean = float(np.mean(lab_v))
    nrmse = (rmse / lab_mean) * 100 if lab_mean > 1e-10 else 0.0
    return nrmse


def main():
    print("=" * 80, flush=True)
    print("R129af: Apply per-batch PAA_c and m_paa to COMBINED dict", flush=True)
    print("=" * 80, flush=True)

    # Step 1: Compute baseline PAA nRMSE for each batch
    print("\n--- Step 1: Baseline PAA nRMSE (default PAA_c=530000, m_paa=1.05) ---", flush=True)
    baseline_results = {}
    for b in GOLDEN:
        v3 = pd.read_csv(f"data/processed/batches/batch_{b:02d}.csv")
        cp = COMBINED[b]
        params = build_params(cp, paa_c=530000.0, m_paa=1.05)
        sim, _ = simulate_open_loop(b, params)
        paa_n = compute_channel_nrmse(sim, v3, "PAA", "PAA_offline")
        ym = yield_metrics(sim, v3)
        yield_err = ym["rel_err_total"]
        baseline_results[b] = {"paa_nrmse": paa_n, "yield_err": yield_err}
        print("  Batch {:2d}: PAA={:.1f}% yield={:+.4f}".format(b, paa_n, yield_err), flush=True)

    # Step 2: Compare with v1 best and decide
    print("\n--- Step 2: Compare with v1 best ---", flush=True)
    apply_results = {}
    for b in GOLDEN:
        base = baseline_results[b]
        v1 = V1_BEST[b]
        
        if v1["paa_nrmse"] == float('inf'):
            apply_results[b] = {"PAA_c": 530000.0, "m_paa": 1.05, "applied": False,
                                 "reason": "v1 inf (structural)"}
            print("  Batch {:2d}: SKIP (v1 inf, structural)".format(b), flush=True)
        elif v1["paa_nrmse"] < base["paa_nrmse"] and abs(v1["yield_err"]) < 0.03:
            apply_results[b] = {"PAA_c": float(v1["PAA_c"]), "m_paa": float(v1["m_paa"]),
                                 "applied": True,
                                 "improvement": base["paa_nrmse"] - v1["paa_nrmse"]}
            print("  Batch {:2d}: APPLY PAA_c={} m_paa={} ({}%→{}%, yield={:+.4f})".format(
                b, v1["PAA_c"], v1["m_paa"], base["paa_nrmse"], v1["paa_nrmse"], v1["yield_err"]), flush=True)
        elif v1["paa_nrmse"] < base["paa_nrmse"] and abs(v1["yield_err"]) < 0.05:
            apply_results[b] = {"PAA_c": float(v1["PAA_c"]), "m_paa": float(v1["m_paa"]),
                                 "applied": True,
                                 "improvement": base["paa_nrmse"] - v1["paa_nrmse"]}
            print("  Batch {:2d}: APPLY (marginal yield {:+.4f}) PAA_c={} m_paa={} ({}%→{}%)".format(
                b, v1["yield_err"], v1["PAA_c"], v1["m_paa"], base["paa_nrmse"], v1["paa_nrmse"]), flush=True)
        else:
            apply_results[b] = {"PAA_c": 530000.0, "m_paa": 1.05, "applied": False,
                                 "reason": "v1 worse or yield too high"}
            print("  Batch {:2d}: KEEP DEFAULT (v1={}% > base={}%, or yield={:+.4f})".format(
                b, v1["paa_nrmse"], base["paa_nrmse"], v1["yield_err"]), flush=True)

    # Step 3: Write updated COMBINED dict
    print("\n--- Step 3: Write updated COMBINED dict ---", flush=True)
    
    # Build the new COMBINED dict as a string
    lines = []
    for b in GOLDEN:
        cp = COMBINED[b]
        ar = apply_results[b]
        
        # Start with base params
        params = dict(cp)
        if ar["applied"]:
            params["PAA_c"] = ar["PAA_c"]
            params["m_paa"] = ar["m_paa"]
        
        # Format as dict entry
        parts = []
        for k, v in params.items():
            if isinstance(v, list):
                parts.append('"{}": {}'.format(k, v))
            elif isinstance(v, float) and v < 1:
                parts.append('"{}": {}'.format(k, v))
            else:
                parts.append('"{}": {}'.format(k, v))
        line = "    {:2d}: {{{}}}".format(b, ", ".join(parts))
        lines.append(line)
    
    combined_str = "COMBINED = {\n" + ",\n".join(lines) + "\n}"
    
    # Write to a new file
    dst = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "tools", "diag_final_validation_v3.py")
    
    # Read the original file and replace COMBINED dict
    src = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "tools", "diag_final_validation_v2.py")
    with open(src, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Find COMBINED dict start and end
    start_marker = "COMBINED = {"
    end_marker = "\n}"
    start_idx = content.find(start_marker)
    end_idx = content.find(end_marker, start_idx) + len(end_marker)
    
    new_content = content[:start_idx] + combined_str + content[end_idx:]
    
    with open(dst, "w", encoding="utf-8", newline="") as f:
        f.write(new_content)
    
    print("  Written: %s" % dst, flush=True)
    
    # Step 4: Save apply results
    dst_json = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "runs", "p3", "d9_paa_apply_v1.json")
    with open(dst_json, "w", encoding="utf-8") as f:
        json.dump({"baseline": {str(k): v for k, v in baseline_results.items()},
                   "apply_results": {str(k): v for k, v in apply_results.items()}}, f, ensure_ascii=False, indent=2)
    print("  Saved: %s" % dst_json, flush=True)


if __name__ == "__main__":
    main()

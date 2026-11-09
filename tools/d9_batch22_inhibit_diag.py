# -*- coding: utf-8 -*-
"""R129ah: Diagnose Batch 22 biomass growth inhibition.

The simulation produces X~0.7 while V3 has X~21.4 (30x difference).
Check which inhibition term is blocking growth:
- CO2_inhib (depends on CO2d)
- pH_inhib (depends on pH)
- DO_2_inhib_X (depends on DO2)
- T_inhib (depends on T)
- NH3_inhib (depends on NH3)
- PAA_inhib_X (depends on PAA)
"""
import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))

from simulate import simulate_open_loop


def main():
    b = 22
    v3 = pd.read_csv(f"data/processed/batches/batch_{b:02d}.csv")
    params = {"mux": 0.35, "mup": 0.065, "alpha_kla": 85.0, "PAA_c": 530000.0,
              "N_conc_paa": 150000.0, "c_oil": 1000.0, "dist_flag": 1,
              "dist_tcin_asym": 20, "m_s": 0.029, "m_s_schedule": [(110, 0.010)],
              "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40}
    sim, _ = simulate_open_loop(b, params)

    print("=" * 80, flush=True)
    print("R129ah: Batch 22 biomass growth inhibition diagnosis", flush=True)
    print("=" * 80, flush=True)

    # Check key variables at multiple time points
    n = len(sim)
    for t_idx in [0, n//4, n//2, 3*n//4, n-1]:
        t = sim["time_h"].iloc[t_idx]
        x_sim = sim["X"].iloc[t_idx]
        x_v3 = v3["X"].iloc[t_idx] if "X" in v3 and t_idx < len(v3) else np.nan

        print("\n--- t={:.0f}h ---".format(t), flush=True)
        print("  X: sim={:.2f} v3={:.2f}".format(x_sim, x_v3 if not np.isnan(x_v3) else -1), flush=True)

        # Check CO2
        if "CO2d" in sim:
            co2d = sim["CO2d"].iloc[t_idx]
            print("  CO2d: {:.1f} (sim)".format(co2d), flush=True)
        if "CO2outgas" in v3 and t_idx < len(v3):
            co2_v3 = v3["CO2outgas"].iloc[t_idx]
            print("  CO2outgas: {:.1f} (v3)".format(co2_v3), flush=True)

        # Check pH
        if "pH" in sim:
            ph = sim["pH"].iloc[t_idx]
            print("  pH: {:.2f} (sim)".format(ph), flush=True)

        # Check DO2
        if "DO2" in sim:
            do2 = sim["DO2"].iloc[t_idx]
            print("  DO2: {:.1f}% (sim)".format(do2), flush=True)

        # Check T
        if "T" in sim:
            tt = sim["T"].iloc[t_idx]
            print("  T: {:.1f} (sim)".format(tt), flush=True)

        # Check NH3
        if "NH3" in sim:
            nh3 = sim["NH3"].iloc[t_idx]
            print("  NH3: {:.1f} (sim)".format(nh3), flush=True)

        # Check PAA
        if "PAA" in sim:
            paa = sim["PAA"].iloc[t_idx]
            print("  PAA: {:.1f} (sim)".format(paa), flush=True)

        # Check S
        if "S" in sim:
            s = sim["S"].iloc[t_idx]
            print("  S: {:.4f} (sim)".format(s), flush=True)

        # Check A0, A1
        if "A0" in sim:
            a0 = sim["A0"].iloc[t_idx]
            a1 = sim["A1"].iloc[t_idx]
            print("  A0={:.2f} A1={:.2f} (sim)".format(a0, a1), flush=True)

    # Check V3 X_offline trajectory
    print("\n--- V3 X_offline trajectory ---", flush=True)
    if "X_offline" in v3:
        v3_x = v3["X_offline"].dropna()
        for i in range(0, len(v3_x), 4):
            t = v3["time_h"].iloc[i] if "time_h" in v3 else i
            print("  t={}: X_offline={:.2f}".format(t, v3_x.iloc[i]), flush=True)

    # Check what happens if we disable CO2 inhibition
    # by checking the CO2 concentration range
    print("\n--- CO2 concentration range ---", flush=True)
    if "CO2d" in sim:
        co2d_sim = sim["CO2d"]
        print("  Sim CO2d: min={:.1f} max={:.1f} mean={:.1f}".format(
            co2d_sim.min(), co2d_sim.max(), co2d_sim.mean()), flush=True)
    if "CO2d" in v3:
        co2d_v3 = v3["CO2d"]
        print("  V3 CO2d: min={:.1f} max={:.1f} mean={:.1f}".format(
            co2d_v3.min(), co2d_v3.max(), co2d_v3.mean()), flush=True)

    # Check if CO2 is the culprit by looking at the CO2_inhib formula
    # CO2_inhib = 1 / (1 + (CO2 / K_CO2)^n)
    # From params.py: K_CO2 = par[26] = 0.5 (typical)
    # If CO2 >> K_CO2, CO2_inhib -> 0

    # Let me check the actual CO2 values
    print("\n--- CO2_inhib calculation ---", flush=True)
    # The CO2_inhib depends on the dissolved CO2 (CO2d)
    # From model.py: CO2_inhib = 1 / (1 + (y[8] / K_CO2) ** n_CO2)
    # where y[8] is CO2d and K_CO2 = par[26]
    # Let me check the params.py for K_CO2

    # Also check the growth rate directly
    print("\n--- Growth rate analysis ---", flush=True)
    # mu_e = mux_max * pH_inhib * NH3_inhib * T_inhib * DO_2_inhib_X * CO2_inhib * PAA_inhib_X
    # r_e1 = mu_e * a_0 * s / (K_e + s)
    # If mu_e is very low, the growth is blocked

    # The key question: which inhibition term is reducing mu_e?
    # Let me check the model params for the inhibition thresholds
    print("  Checking model params for inhibition thresholds...", flush=True)

    # Read params.py
    params_path = os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1", "params.py")
    with open(params_path, "r", encoding="utf-8") as f:
        params_content = f.read()

    # Find CO2-related params
    for line in params_content.split("\n"):
        if "CO2" in line.upper() or "co2" in line.lower():
            print("  {}".format(line.strip()), flush=True)


if __name__ == "__main__":
    main()

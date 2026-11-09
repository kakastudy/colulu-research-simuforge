# -*- coding: utf-8 -*-
"""R129ah: Diagnose mu_h (k4) value during Batch 22 simulation.

k4 = exp((B_1 + B_2*ph_val + B_3*T + B_4*ph_val^2) + B_5*T^2)

If T is in Kelvin (298.3), k4 = exp(2.2) = 9.07 (very high).
If T is in Celsius (25.3), k4 = exp(-53.8) ≈ 0 (no degradation).

The simulation shows P=36.2 (high), suggesting mu_h is low.
Let's check what's actually happening.
"""
import os
import sys
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))

from params import make_params


def compute_k4(ph, T, par):
    """Compute k4 from pH and T."""
    B_1 = par[80]
    B_2 = par[81]
    B_3 = par[82]
    B_4 = par[83]
    B_5 = par[84]
    ph_val = -np.log10(max(ph, 1e-12))
    k4 = np.exp((B_1 + B_2 * ph_val + B_3 * T + B_4 * ph_val**2) + B_5 * T**2)
    return k4


def main():
    par = make_params()

    print("=" * 80, flush=True)
    print("R129ah: mu_h (k4) diagnosis for Batch 22", flush=True)
    print("=" * 80, flush=True)

    print("\nB parameters:", flush=True)
    for i, name in enumerate(["B_1", "B_2", "B_3", "B_4", "B_5"]):
        print("  par[{}] = {} = {}".format(80 + i, name, par[80 + i]), flush=True)

    # Batch 22 conditions at different time points
    conditions = [
        (6.48, 298.3, "t=0h (initial)"),
        (6.63, 306.9, "t=58h"),
        (6.45, 306.0, "t=115h"),
        (6.02, 306.9, "t=173h"),
        (6.33, 305.5, "t=230h"),
    ]

    print("\n--- k4 computation (T in Kelvin) ---", flush=True)
    for ph, T, label in conditions:
        k4_k = compute_k4(ph, T, par)
        # Also compute with T in Celsius
        T_c = T - 273.15
        k4_c = compute_k4(ph, T_c, par)
        print("  {}: pH={:.2f} T={:.1f}K({:.1f}C)".format(label, ph, T, T_c), flush=True)
        print("    k4(T_K) = {:.6f}  mu_h = {:.6f}".format(k4_k, k4_k), flush=True)
        print("    k4(T_C) = {:.6e}  mu_h = {:.6e}".format(k4_c, k4_c), flush=True)

    # Check what the model actually uses
    # The model uses y[7] directly, which is in Kelvin
    # But maybe the model converts T to Celsius somewhere

    # Let's check the initial state T value
    import pandas as pd
    from simulate import simulate_open_loop

    params = {"mux": 0.35, "mup": 0.065, "alpha_kla": 85.0, "PAA_c": 530000.0,
              "N_conc_paa": 150000.0, "c_oil": 1000.0, "dist_flag": 1,
              "dist_tcin_asym": 20, "m_s": 0.029, "m_s_schedule": [(110, 0.010)],
              "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40}
    sim, _ = simulate_open_loop(22, params)

    print("\n--- Simulation T values ---", flush=True)
    for t_idx in [0, len(sim)//4, len(sim)//2, 3*len(sim)//4, len(sim)-1]:
        t = sim["time_h"].iloc[t_idx]
        T_val = sim["T"].iloc[t_idx]
        pH_val = sim["pH"].iloc[t_idx]
        k4_k = compute_k4(pH_val, T_val, par)
        k4_c = compute_k4(pH_val, T_val - 273.15, par)
        print("  t={:.0f}h: T={:.1f} pH={:.2f} k4(K)={:.6f} k4(C)={:.6e}".format(
            t, T_val, pH_val, k4_k, k4_c), flush=True)

    # Check the P trajectory
    print("\n--- P trajectory ---", flush=True)
    for t_idx in [0, len(sim)//4, len(sim)//2, 3*len(sim)//4, len(sim)-1]:
        t = sim["time_h"].iloc[t_idx]
        P_val = sim["P"].iloc[t_idx]
        print("  t={:.0f}h: P={:.2f}".format(t, P_val), flush=True)


if __name__ == "__main__":
    main()

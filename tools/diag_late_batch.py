# -*- coding: utf-8 -*-
"""Diagnose late-batch growth dynamics: why doesn't X decline?"""
import sys, os
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from simulate import simulate_open_loop
from model import rhs
from params import make_params

params = {"mux": 0.41, "mup": 0.041, "alpha_kla": 85.0, "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0}
sim, v3 = simulate_open_loop(1, params)

print("=== Late-batch dynamics (batch 1) ===")
print(f"{'t':>6s} {'S':>8s} {'A0':>6s} {'A1':>6s} {'X':>6s} {'mu_e':>6s} {'r_e1':>6s} {'r_b0':>6s} {'r_d1':>6s} {'S_feed':>8s} {'S_cons':>8s}")

par = make_params(mux=0.41, mup=0.041, alpha_kla=85.0, PAA_c=530000.0, N_conc_paa=150000.0, c_oil=1000.0)

for t in [100, 120, 140, 156, 170, 180, 190, 196, 200, 204, 208, 212]:
    i = sim[sim.time_h <= t].index[-1]
    row = sim.iloc[i]
    y = np.zeros(33)
    y[0] = row["S"]; y[1] = row["DO2"]; y[3] = row["P"]; y[4] = row["V"]
    y[6] = 10**(-row["pH"]); y[7] = row["T"]
    y[11] = row["A0"]; y[12] = row["A1"]; y[13] = row["A3"]; y[14] = row["A4"]
    y[10] = row["A0"] + row["A1"] + row["A3"] + row["A4"]
    y[28] = row["CO2d"] if "CO2d" in row else 0.0
    y[29] = row["PAA"] if "PAA" in row else 0.0
    y[30] = row["NH3"] if "NH3" in row else 0.0

    # Build inp1
    from simulate import build_inp1
    v3_row = v3[v3.time_h <= t].iloc[-1]
    inp1 = build_inp1(v3_row)

    # Compute rates via rhs (returns dy)
    dy = rhs(t, y, inp1, par)

    # Extract from dy
    s = y[0]
    a_0 = y[11]
    a_1 = y[12]
    a_3 = y[13]
    a_4 = y[14]
    X = a_0 + a_1 + a_3 + a_4

    print(f"{t:>6.1f} {s:>8.4f} {a_0:>6.2f} {a_1:>6.2f} {X:>6.1f} "
          f"dA0={dy[11]:>+6.3f} dA1={dy[12]:>+6.3f} dX={dy[11]+dy[12]+dy[13]+dy[14]:>+6.3f} "
          f"Fs={inp1[1]:>5.0f} S_rate={dy[0]:>+6.3f}")

# Also check: what is S in the sim at t=156-200?
print("\n=== S trajectory ===")
for t in [140, 150, 156, 160, 170, 180, 190, 196, 200, 204]:
    i = sim[sim.time_h <= t].index[-1]
    row = sim.iloc[i]
    print(f"t={t}: S={row['S']:.6f} A0={row['A0']:.2f} A1={row['A1']:.2f} X={row['A0']+row['A1']:.1f} "
          f"CO2d={row['CO2d']:.2f}")

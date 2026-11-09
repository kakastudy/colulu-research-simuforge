# -*- coding: utf-8 -*-
"""Diagnose batch 8 early crash: what inhibits growth at t=100?"""
import sys, os
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from simulate import simulate_open_loop
from model import rhs
from params import make_params
from simulate import build_inp1

params = {"mux": 0.41, "mup": 0.041, "alpha_kla": 85.0, "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0}
par = make_params(mux=0.41, mup=0.041, alpha_kla=85.0, PAA_c=530000.0, N_conc_paa=150000.0, c_oil=1000.0)
sim, v3 = simulate_open_loop(8, params)

print("=== Batch 8: inhibition factors at key times ===")
print(f"{'t':>6s} {'S':>8s} {'pH':>6s} {'T':>6s} {'DO2':>6s} {'CO2d':>6s} {'mu_e':>6s} {'X':>6s} {'dS/dt':>8s}")

for t in [4.4, 24.4, 48.4, 70.4, 80.4, 90.4, 100.4, 110.4, 120.4, 140.4, 156.4, 196.4]:
    i = sim[sim.time_h <= t].index[-1]
    row = sim.iloc[i]

    y = np.zeros(33)
    y[0] = row["S"]; y[1] = row["DO2"]; y[3] = row["P"]; y[4] = row["V"]
    y[6] = 10**(-row["pH"]); y[7] = row["T"]
    y[11] = row["A0"]; y[12] = row["A1"]; y[13] = row["A3"]; y[14] = row["A4"]
    y[10] = row["A0"] + row["A1"] + row["A3"] + row["A4"]
    y[28] = row["CO2d"]; y[27] = row["CO2outgas"]
    y[29] = row["PAA"]; y[30] = row["NH3"]

    v3_row = v3[v3.time_h <= t].iloc[-1]
    inp1 = build_inp1(v3_row)

    dy = rhs(t, y, inp1, par)

    X = row["A0"] + row["A1"]
    print(f"{t:>6.1f} {row['S']:>8.3f} {row['pH']:>6.2f} {row['T']:>6.2f} "
          f"{row['DO2']:>6.1f} {row['CO2d']:>6.2f} {row['mux']:>6.3f} {X:>6.1f} "
          f"{dy[0]:>+8.3f}")

# -*- coding: utf-8 -*-
"""Check what changes between t=80-90 in batch 8: MVs, pH dynamics."""
import sys, os
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from simulate import simulate_open_loop

params = {"mux": 0.41, "mup": 0.041, "alpha_kla": 85.0, "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0}
sim, v3 = simulate_open_loop(8, params)

print("=== Batch 8: MVs and state around pH crash ===")
print(f"{'t':>6s} {'pH':>6s} {'S':>8s} {'NH3':>8s} {'Fa':>6s} {'Fb':>6s} {'Fh':>6s} {'Fw':>6s} "
      f"{'NH3s':>6s} {'CO2d':>6s} {'X':>6s} {'ph_prod':>8s}")

for t in [70, 75, 80, 82, 84, 86, 88, 90, 95, 100]:
    i = sim[sim.time_h <= t].index[-1]
    s = sim.iloc[i]
    X = s["A0"] + s["A1"] + s["A3"] + s["A4"]
    # Approximate ph_prod = r_b0 + r_e1 + r_d4 + r_d1 + m_ph * X
    # r_b0 = mu_a0 * a_1 * s/(K_b+s)
    # r_e1 = mu_e * a_0 * s/(K_e+s)
    # Use sim's mux and mup states
    s_val = s["S"]
    K_b = 0.05; K_e = 0.009
    mu_a0 = s["mup"]  # This is mu_X state, not mu_a0
    mu_e = s["mux"]   # This is mu_e state

    # Actually, mu_a0 = par[1] (mux_max) * inhibition factors
    # mu_e = par[1] * inhibition factors
    # The sim's 'mux' and 'mup' state variables track these

    from model import rhs
    from params import make_params
    from simulate import build_inp1

    par = make_params(mux=0.41, mup=0.041, alpha_kla=85.0, PAA_c=530000.0, N_conc_paa=150000.0, c_oil=1000.0)
    y = np.zeros(33)
    y[0] = s["S"]; y[1] = s["DO2"]; y[3] = s["P"]; y[4] = s["V"]
    y[6] = 10**(-s["pH"]); y[7] = s["T"]
    y[11] = s["A0"]; y[12] = s["A1"]; y[13] = s["A3"]; y[14] = s["A4"]
    y[10] = s["A0"] + s["A1"] + s["A3"] + s["A4"]
    y[28] = s["CO2d"]; y[27] = s["CO2outgas"]
    y[29] = s["PAA"]; y[30] = s["NH3"]

    v3r = v3[v3.time_h <= t].iloc[-1]
    inp1 = build_inp1(v3r)
    dy = rhs(t, y, inp1, par)

    # Extract rate terms from the full rhs
    # ph_prod is not directly in rhs output, but we can compute it
    # ph_prod = r_b0 + r_e1 + r_d4 + r_d1 + m_ph * total_X
    # We need the individual rates

    print(f"{t:>6.1f} {s['pH']:>6.2f} {s['S']:>8.3f} {s['NH3']:>8.1f} "
          f"{v3r['Fa']:>6.1f} {v3r['Fb']:>6.1f} {v3r['Fh']:>6.1f} {v3r['Fw']:>6.1f} "
          f"{v3r['NH3_shots']:>6.1f} {s['CO2d']:>6.2f} {X:>6.1f} "
          f"{dy[6]:>+8.2e}")

# -*- coding: utf-8 -*-
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from simulate import simulate_open_loop
import pandas as pd

params = {"mux": 0.41, "mup": 0.041, "alpha_kla": 85.0, "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0}
sim, d = simulate_open_loop(1, params)
print("=== V and Wt comparison ===")
for t in [4.4, 24.4, 48.4, 100.4, 156.4, 196.4, 200.4]:
    si = sim[sim.time_h <= t].iloc[-1]
    vi = d[d.time_h <= t].iloc[-1]
    print(f"t={t}: V sim={si['V']:.0f} v3={vi['V']:.0f} | Wt sim={si['Wt']:.1f} v3={vi['Wt']:.1f}")

# Check substrate input per volume
print("\n=== Substrate input (g/L/h) ===")
for t in [4.4, 24.4, 48.4, 100.4, 156.4, 196.4]:
    si = sim[sim.time_h <= t].iloc[-1]
    vi = d[d.time_h <= t].iloc[-1]
    fs, foil = si['Fs'], si['Foil']
    vs = si['V']
    input_sim = (fs * 600 + foil * 1000) / vs
    input_v3 = (vi['Fs'] * 600 + vi['Foil'] * 1000) / vi['V']
    print(f"t={t}: sim_input={input_sim:.3f} v3_input={input_v3:.3f}")

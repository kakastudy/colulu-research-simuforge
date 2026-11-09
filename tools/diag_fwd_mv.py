# -*- coding: utf-8 -*-
"""Forward-looking MV test: compare with V3 after fixing MV timing."""
import sys
import os
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from simulate import simulate_open_loop, yield_metrics

print("=== Forward-looking MV (mux=0.41, kla=85, mup=0.041) ===")
params = {"mux": 0.41, "mup": 0.041, "alpha_kla": 85.0, "PAA_c": 530000.0,
          "N_conc_paa": 150000.0, "c_oil": 1000.0}
sim, d = simulate_open_loop(1, params)

co2d_max = sim["CO2d"].max()
v3 = d

# Key comparisons
for t_target in [4.4, 24.4, 48.4, 100.4, 156.4, 196.4, 200.4]:
    si = sim[sim.time_h <= t_target].iloc[-1]
    vi = v3[v3.time_h <= t_target].iloc[-1]
    x_sim = si["A0"] + si["A1"]
    print(f"t={t_target}: S {si['S']:.3f}/{vi['S']:.3f} P {si['P']:.2f}/{vi['P']:.2f} "
          f"X {x_sim:.1f} CO2 {si['CO2outgas']:.2f}/{vi['CO2outgas']:.2f} "
          f"DO2 {si['DO2']:.1f}/{vi['DO2']:.1f} CO2d {si['CO2d']:.2f}")

row200 = sim[sim.time_h <= 200.0].iloc[-1]
x_pre = row200["A0"] + row200["A1"]
p_pre = row200["P"]
print(f"\nX@200={x_pre:.1f} P@200={p_pre:.1f} CO2d_max={co2d_max:.2f}")
y = yield_metrics(sim, d)
print(f"yield={y['total_sim_g']:,.0f} (V3={y['total_v3_g']:,.0f}) rel_err={y['rel_err']:+.1%}")
crashed = "CRASH" if co2d_max > 7.57 else "ok"
print(f"Status: {crashed}")

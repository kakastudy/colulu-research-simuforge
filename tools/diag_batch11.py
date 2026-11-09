# -*- coding: utf-8 -*-
"""Analyze batch 11: why doesn't it crash?"""
import sys, os
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from simulate import simulate_open_loop

d = pd.read_csv("data/processed/batches/batch_11.csv")
print(f"Batch 11: {len(d)} rows, time range {d.time_h.min():.1f}-{d.time_h.max():.1f}")
print(f"FaultFlag: {d.FaultFlag.unique()}")
print()

# Check key V3 trajectories
for t in [4.4, 24.4, 48.4, 100.4, 156.4, 196.4, 200.4]:
    vi = d[d.time_h <= t].iloc[-1]
    print(f"t={t}: S={vi['S']:.3f} P={vi['P']:.2f} CO2={vi['CO2outgas']:.2f} "
          f"DO2={vi['DO2']:.1f} X_off={vi['X_offline']:.2f} "
          f"Fg={vi['Fg']:.0f} Fs={vi['Fs']:.0f}")

# Check X_offline
xoff = pd.to_numeric(d['X_offline'], errors='coerce').dropna()
print(f"\nX_offline: {len(xoff)} points, range {xoff.min():.1f}-{xoff.max():.1f}")

# Run sim with nominal params
params = {"mux": 0.41, "mup": 0.041, "alpha_kla": 85.0, "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0}
sim, _ = simulate_open_loop(11, params)
print("\n=== Sim vs V3 ===")
for t in [4.4, 24.4, 48.4, 100.4, 156.4, 196.4, 200.4]:
    si = sim[sim.time_h <= t].iloc[-1]
    vi = d[d.time_h <= t].iloc[-1]
    x_sim = si['A0'] + si['A1']
    print(f"t={t}: X {x_sim:.1f}/{vi['X_offline']:.1f} P {si['P']:.1f}/{vi['P']:.1f} "
          f"CO2 {si['CO2outgas']:.2f}/{vi['CO2outgas']:.2f} CO2d {si['CO2d']:.2f}")

print(f"\nCO2d_max={sim['CO2d'].max():.2f} (threshold 7.57)")

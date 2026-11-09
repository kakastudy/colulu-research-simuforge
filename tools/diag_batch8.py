# -*- coding: utf-8 -*-
"""Investigate batch 8: why is sim yield so low vs V3?"""
import sys, os
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from simulate import simulate_open_loop, yield_metrics

d = pd.read_csv("data/processed/batches/batch_08.csv")
print(f"Batch 8: {len(d)} rows, time {d.time_h.min():.1f}-{d.time_h.max():.1f}")
print(f"FaultFlag: {d.FaultFlag.unique()}")

# V3 key trajectories
print("\n=== V3 Trajectory ===")
for t in [4.4, 24.4, 48.4, 100.4, 156.4, 196.4, 200.4]:
    vi = d[d.time_h <= t].iloc[-1]
    xoff_val = vi['X_offline'] if pd.notna(vi['X_offline']) else 0
    print(f"t={t}: S={vi['S']:.3f} P={vi['P']:.2f} CO2={vi['CO2outgas']:.2f} "
          f"DO2={vi['DO2']:.1f} X_off={xoff_val:.2f} "
          f"Fg={vi['Fg']:.0f} Fs={vi['Fs']:.0f}")

# X_offline
xoff = pd.to_numeric(d['X_offline'], errors='coerce').dropna()
print(f"\nX_offline: {len(xoff)} points, range {xoff.min():.1f}-{xoff.max():.1f}")
print(f"X_offline values: {xoff.tolist()[:10]}...")

# Run sim
params = {"mux": 0.41, "mup": 0.041, "alpha_kla": 85.0, "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0}
sim, _ = simulate_open_loop(8, params)

print("\n=== Sim vs V3 ===")
for t in [4.4, 24.4, 48.4, 100.4, 156.4, 196.4, 200.4]:
    si = sim[sim.time_h <= t].iloc[-1]
    vi = d[d.time_h <= t].iloc[-1]
    x_sim = si['A0'] + si['A1']
    xoff_val = vi['X_offline'] if pd.notna(vi['X_offline']) else 0
    print(f"t={t}: X {x_sim:.1f}/{xoff_val:.1f} "
          f"P {si['P']:.1f}/{vi['P']:.1f} S {si['S']:.3f}/{vi['S']:.3f} "
          f"CO2 {si['CO2outgas']:.2f}/{vi['CO2outgas']:.2f}")

ym = yield_metrics(sim, d)
print(f"\nYield: sim={ym['total_sim_g']:,.0f} V3={ym['total_v3_g']:,.0f} err={ym['rel_err_total']:+.1%}")
print(f"CO2d_max={sim['CO2d'].max():.2f}")

# Check Fremoved (harvest)
print(f"\nFremoved: sim sum={sim['Fremoved'].sum():.0f} V3 sum={d['Fremoved'].sum():.0f}")
print(f"Fremoved nonzero count: sim={(sim['Fremoved']!=0).sum()} V3={(d['Fremoved']!=0).sum()}")
print(f"P at harvest: sim={sim['P'].max():.2f} V3={d['P'].max():.2f}")
print(f"V at end: sim={sim['V'].iloc[-1]:.0f} V3={d['V'].iloc[-1]:.0f}")

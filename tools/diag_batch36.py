# -*- coding: utf-8 -*-
"""Investigate batch 36: sim overproduces P (+118% yield)."""
import sys, os
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from simulate import simulate_open_loop, yield_metrics

params = {"mux": 0.41, "mup": 0.041, "alpha_kla": 85.0, "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0}
sim, v3 = simulate_open_loop(36, params)

print(f"Batch 36: {len(v3)} rows, time {v3.time_h.min():.1f}-{v3.time_h.max():.1f}")
print(f"FaultFlag: {v3.FaultFlag.unique()}")

ym = yield_metrics(sim, v3)
print(f"\nYield: sim={ym['total_sim_g']:,.0f} V3={ym['total_v3_g']:,.0f} err={ym['rel_err_total']:+.1%}")
print(f"  harvested: sim={ym['harvested_sim_g']:,.0f} V3={ym['harvested_v3_g']:,.0f}")
print(f"  end_in_vessel: sim={ym['end_in_vessel_sim_g']:,.0f} V3={ym['end_in_vessel_v3_g']:,.0f}")
print(f"CO2d_max={sim['CO2d'].max():.2f}")

print("\n=== Sim vs V3 at key times ===")
for t in [4.4, 24.4, 48.4, 100.4, 156.4, 196.4, 200.4, 226.4]:
    si = sim[sim.time_h <= t].iloc[-1] if sim.time_h.max() >= t else sim.iloc[-1]
    vi = v3[v3.time_h <= t].iloc[-1] if v3.time_h.max() >= t else v3.iloc[-1]
    x_sim = si['A0'] + si['A1']
    xoff_val = vi['X_offline'] if pd.notna(vi['X_offline']) else 0
    print(f"t={t}: X {x_sim:.1f}/{xoff_val:.1f} P {si['P']:.1f}/{vi['P']:.1f} "
          f"S {si['S']:.3f}/{vi['S']:.3f} pH {si['pH']:.2f}/{vi['pH']:.2f} "
          f"T {si['T']:.1f}/{vi['T']:.1f} Fg {si['Fg']:.0f}/{vi['Fg']:.0f}")

# Check Fremoved
print(f"\nFremoved: sim sum={sim['Fremoved'].sum():.0f} V3 sum={v3['Fremoved'].sum():.0f}")
print(f"P at harvest: sim={sim['P'].max():.2f} V3={v3['P'].max():.2f}")
print(f"V at end: sim={sim['V'].iloc[-1]:.0f} V3={v3['V'].iloc[-1]:.0f}")

# X_offline
xoff = pd.to_numeric(v3['X_offline'], errors='coerce').dropna()
print(f"\nX_offline: {len(xoff)} points, range {xoff.min():.1f}-{xoff.max():.1f}")

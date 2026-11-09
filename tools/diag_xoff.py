# -*- coding: utf-8 -*-
"""Check V3 X_offline trajectory and compare with sim."""
import sys, os
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from simulate import simulate_open_loop

d = pd.read_csv("data/processed/batches/batch_01.csv")
xoff = pd.to_numeric(d["X_offline"], errors="coerce").dropna()
print("=== V3 X_offline (non-NaN) ===")
for _, r in d[pd.to_numeric(d["X_offline"], errors="coerce").notna()].iterrows():
    print(f"  t={r['time_h']:.1f}: X_offline={r['X_offline']:.3f}")

params = {"mux": 0.41, "mup": 0.041, "alpha_kla": 85.0, "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0}
sim, _ = simulate_open_loop(1, params)
print("\n=== Sim X trajectory ===")
for t in [4.4, 12.4, 24.4, 48.4, 100.4, 156.4, 196.4, 200.4]:
    si = sim[sim.time_h <= t].iloc[-1]
    x = si["A0"] + si["A1"]
    print(f"  t={t}: X={x:.2f} (A0={si['A0']:.2f} A1={si['A1']:.2f})")

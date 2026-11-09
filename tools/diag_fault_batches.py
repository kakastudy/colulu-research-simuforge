# -*- coding: utf-8 -*-
"""Check fault batch characteristics for fault reproducibility."""
import sys, os
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from simulate import simulate_open_loop

for batch_no in [91, 92]:
    d = pd.read_csv(f"data/processed/batches/batch_{batch_no:02d}.csv")
    print(f"=== Batch {batch_no} ===")
    print(f"  Rows: {len(d)}, Time: {d.time_h.min():.1f}-{d.time_h.max():.1f}")
    print(f"  FaultFlag: {d.FaultFlag.unique()}")

    # Check MVs for anomalies
    mvs = ["Fg", "Fs", "Fa", "Fb", "Fc", "Fh", "Fw", "RPM", "Fremoved", "Fpaa", "Foil", "NH3_shots"]
    for mv in mvs:
        vals = d[mv].to_numpy(float)
        print(f"  {mv:>12s}: {vals.min():.1f} ~ {vals.max():.1f} (mean={vals.mean():.1f})")

    # Check key process variables
    print(f"  S: {d.S.min():.3f} ~ {d.S.max():.3f}")
    print(f"  P: {d.P.min():.2f} ~ {d.P.max():.2f}")
    print(f"  CO2outgas: {d.CO2outgas.min():.2f} ~ {d.CO2outgas.max():.2f}")
    print(f"  DO2: {d.DO2.min():.1f} ~ {d.DO2.max():.1f}")
    print(f"  pH: {d.pH.min():.2f} ~ {d.pH.max():.2f}")
    t_vals = pd.to_numeric(d["T"], errors="coerce").dropna()
    print(f"  T: {t_vals.min():.2f} ~ {t_vals.max():.2f}")
    print(f"  X_offline: {pd.to_numeric(d.X_offline, errors='coerce').min():.2f} ~ {pd.to_numeric(d.X_offline, errors='coerce').max():.2f}")

    # Run sim with nominal params
    params = {"mux": 0.41, "mup": 0.041, "alpha_kla": 85.0, "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0}
    sim, _ = simulate_open_loop(batch_no, params)
    print(f"  Sim: CO2d_max={sim['CO2d'].max():.2f} "
          f"yield={sim['A0'].iloc[-1]+sim['A1'].iloc[-1]:.1f}g "
          f"{'CRASH' if sim['CO2d'].max() > 7.57 else 'ok'}")
    print()

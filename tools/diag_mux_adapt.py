# -*- coding: utf-8 -*-
"""Check if k>65 mux adaptation triggers in sim for batch 36."""
import sys, os
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from simulate import simulate_open_loop

params = {"mux": 0.41, "mup": 0.041, "alpha_kla": 85.0,
          "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0}
sim, _ = simulate_open_loop(36, params)

# The mux state variable is in the sim output
mux_state = sim["mux"].to_numpy(float)
t = sim["time_h"].to_numpy(float)

# Check when mux starts decreasing
diffs = np.diff(mux_state)
n_negative = np.sum(diffs < 0)

print(f"=== Batch 36: mux state trajectory ===")
print(f"mux range: {mux_state.min():.4f} - {mux_state.max():.4f}")
print(f"Total negative diffs: {n_negative}/{len(diffs)}")

# Check consecutive negative diffs (adaptation requires 63/65)
max_consec = 0
cur = 0
for d in diffs:
    if d < 0:
        cur += 1
        max_consec = max(max_consec, cur)
    else:
        cur = 0
print(f"Max consecutive negative diffs: {max_consec} (need 63 for adaptation)")

# Show mux at key times
for tt in [4.4, 24.4, 48.4, 100.4, 156.4, 196.4, 200.4, 226.4]:
    i = sim[sim.time_h <= tt].index[-1]
    print(f"t={tt}: mux={mux_state[i]:.4f}")

# Check if adaptation triggered (par[1] would change from 0.41)
# We can't directly check par[1], but if mux state dropped significantly,
# it might have triggered
print(f"\nMux state at t=100: {np.interp(100.4, t, mux_state):.4f}")
print(f"Mux state at t=200: {np.interp(200.4, t, mux_state):.4f}")
print(f"If adaptation triggered, par[1] = 5.0 * mux = {5.0 * np.interp(200.4, t, mux_state):.4f}")

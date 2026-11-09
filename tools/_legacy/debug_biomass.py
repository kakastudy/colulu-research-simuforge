import sys; sys.path.insert(0, 'candidate/indpensim/v0.1'); sys.path.insert(0, 'tools/vendor')
import numpy as np, pandas as pd
from simulate import simulate_open_loop

d = pd.read_csv('data/processed/batches/batch_01.csv')
sim, v3 = simulate_open_loop(1, nominal=True)

print('=== Batch 1: Biomass comparison ===')
for t_target in [0, 10, 20, 40, 60, 80, 100]:
    sim_mask = abs(sim['time_h'] - t_target) < 0.15
    v3_mask = abs(v3['time_h'] - t_target) < 0.15
    if sim_mask.any() and v3_mask.any():
        sr = sim[sim_mask].iloc[-1]
        vr = v3[v3_mask].iloc[-1]
        sim_X = sr['A0'] + sr['A1'] + sr['A3'] + sr['A4']
        v3_X = vr['X_offline'] if not pd.isna(vr['X_offline']) else 0
        print(f't={t_target}: sim X={sim_X:.3f} (A0={sr["A0"]:.3f} A1={sr["A1"]:.3f}) | '
              f'V3 X={v3_X:.3f} | '
              f'S sim={sr["S"]:.4f} V3={vr["S"]:.4f}')

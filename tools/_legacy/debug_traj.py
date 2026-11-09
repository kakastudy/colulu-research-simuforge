import sys; sys.path.insert(0, 'candidate/indpensim/v0.1'); sys.path.insert(0, 'tools/vendor')
import numpy as np, pandas as pd
from simulate import simulate_open_loop

d = pd.read_csv('data/processed/batches/batch_01.csv')
sim, v3 = simulate_open_loop(1, nominal=True)

print('=== Batch 1: Sim vs V3 at key time points ===')
for t_target in [0, 10, 20, 40, 60, 80, 100]:
    sim_mask = abs(sim['time_h'] - t_target) < 0.15
    v3_mask = abs(v3['time_h'] - t_target) < 0.15
    if sim_mask.any() and v3_mask.any():
        sr = sim[sim_mask].iloc[-1]
        vr = v3[v3_mask].iloc[-1]
        print(f't={t_target}: S sim={sr["S"]:.4f} V3={vr["S"]:.4f} | '
              f'P sim={sr["P"]:.2f} V3={vr["P"]:.2f} | '
              f'DO2 sim={sr["DO2"]:.1f} V3={vr["DO2"]:.1f} | '
              f'pH sim={sr["pH"]:.2f} V3={vr["pH"]:.2f} | '
              f'V sim={sr["V"]:.0f} V3={vr["V"]:.0f}')

print()
print('=== A1 trajectory (sim only) ===')
for t_target in [0, 10, 20, 40, 60, 80, 100]:
    sim_mask = abs(sim['time_h'] - t_target) < 0.15
    if sim_mask.any():
        sr = sim[sim_mask].iloc[-1]
        print(f't={t_target}: A0={sr["A0"]:.4f} A1={sr["A1"]:.4f} A3={sr["A3"]:.4f} A4={sr["A4"]:.4f}')

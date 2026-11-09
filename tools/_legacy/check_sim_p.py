import pandas as pd
sim = pd.read_csv('data/processed/sim_batch_01.csv')
print('Sim P trajectory (every 10 rows):')
for i in range(0, len(sim), 50):
    r = sim.iloc[i]
    print(f'  t={r["time_h"]:.1f}: P={r["P"]:.4f} S={r["S"]:.4f} A1={r["A1"]:.3f} pH={r["pH"]:.3f}')
print()
print('Sim P around t=80-100:')
for i in range(390, 520, 5):
    r = sim.iloc[i]
    if 75 <= r['time_h'] <= 105:
        print(f'  t={r["time_h"]:.1f}: P={r["P"]:.4f} S={r["S"]:.4f} A1={r["A1"]:.3f} pH={r["pH"]:.3f} DO2={r["DO2"]:.2f}')

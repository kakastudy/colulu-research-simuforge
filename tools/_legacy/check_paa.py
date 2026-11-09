import pandas as pd
d = pd.read_csv('data/processed/batches/batch_01.csv')
print('V3 PAA_offline at key times:')
for t in [0, 10, 20, 40, 60, 80, 100]:
    r = d[abs(d['time_h'] - t) < 0.15]
    if not r.empty:
        print(f't={t}: PAA={r["PAA_offline"].values}')
    else:
        print(f't={t}: N/A')
print()
print('V3 PAA_offline stats:')
print(d['PAA_offline'].describe())

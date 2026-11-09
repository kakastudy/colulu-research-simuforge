# -*- coding: utf-8 -*-
import pandas as pd

v3 = pd.read_csv("data/processed/batches/batch_01.csv")
sim = pd.read_csv("data/processed/sim_batch_01.csv")
print("V3 P / Fb / Fs / Fg t=60..90 step 2:")
for t in range(60, 92, 2):
    v = v3[v3.time_h <= t].iloc[-1]
    s = sim[sim.time_h <= t].iloc[-1]
    print(f"  t={t:5d}  v3P={v['P']:7.3f} simP={s['P']:7.3f}  v3Fb={v['Fb']:7.2f} v3Fs={v['Fs']:6.2f} v3Fg={v['Fg']:6.2f}  simFpaa={v['Fpaa']:5.2f}")

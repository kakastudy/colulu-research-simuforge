# -*- coding: utf-8 -*-
import pandas as pd
import numpy as np

sim = pd.read_csv("data/processed/sim_batch_01.csv")
v3 = pd.read_csv("data/processed/batches/batch_01.csv")
print("sim end-of-batch fine (t=190..226 step 2):")
for t in range(190, 227, 2):
    s = sim[sim.time_h <= t].iloc[-1]
    v = v3[v3.time_h <= t].iloc[-1]
    print(f"  t={t:5d}  simP={s['P']:7.3f} v3P={v['P']:7.3f}  simpH={s['pH']:6.3f} v3pH={v['pH']:6.3f}  "
          f"simPAA={s['PAA']:7.1f}  simDO2={s['DO2']:6.2f} v3DO2={v['DO2']:6.2f}  "
          f"simX={s['X'] if 'X' in s else 0:6.2f}  v3Fb={v['Fb']:7.2f} v3Fpaa={v['Fpaa']:6.2f}")

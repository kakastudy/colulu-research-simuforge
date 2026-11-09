# -*- coding: utf-8 -*-
import pandas as pd
import numpy as np

sim = pd.read_csv("data/processed/sim_batch_01.csv")
v3 = pd.read_csv("data/processed/batches/batch_01.csv")
print("sim pH / P / PAA around t=195..210 step 0.4:")
for t in [195, 195.4, 195.8, 196.2, 196.6, 197.0, 197.4, 197.8, 198.2, 198.6, 199.0, 199.4, 199.8, 200.0, 200.2, 200.4, 200.6, 200.8, 201.0, 201.2, 201.4, 201.6, 201.8, 202.0]:
    s = sim[sim.time_h <= t].iloc[-1]
    v = v3[v3.time_h <= t].iloc[-1]
    print(f"  t={t:6.1f}  simpH={s['pH']:6.3f} simP={s['P']:7.3f} simPAA={s['PAA']:7.1f} simDO2={s['DO2']:6.2f} v3Fb={v['Fb']:7.2f}")

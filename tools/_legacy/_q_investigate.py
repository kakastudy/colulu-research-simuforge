# -*- coding: utf-8 -*-
import pandas as pd
import numpy as np

for b in [8, 11, 16, 22, 60]:
    v3 = pd.read_csv(f"data/processed/batches/batch_{b:02d}.csv")
    print(f"Batch {b:2d}: Q min={v3['Q'].min():.1f} max={v3['Q'].max():.1f} mean={v3['Q'].mean():.1f}")
print()
print("V3 Q values are around 200-700, suggesting it might be in kW or some other unit.")
print("Sim Q (y[8]/1000) values are around 1000-2500, suggesting a different scale.")
print()
v3 = pd.read_csv("data/processed/batches/batch_08.csv")
print("Fg: min={:.1f} max={:.1f} mean={:.1f}".format(v3['Fg'].min(), v3['Fg'].max(), v3['Fg'].mean()))
qfg = v3['Q'] / v3['Fg']
print("Q/Fg: min={:.2f} max={:.2f} mean={:.2f}".format(qfg.min(), qfg.max(), qfg.mean()))
print()
print("Checking if V3 Q might be total heat removal (kW):")
print("  V3 Q mean: {:.1f}".format(v3['Q'].mean()))
print("  This could be the total heat removal rate in kW")

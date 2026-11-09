# -*- coding: utf-8 -*-
"""Check V3 CO2outgas trajectory after Fg drop (t=200) for batch 1."""
import pandas as pd
import numpy as np

d = pd.read_csv("data/processed/batches/batch_01.csv")
print("=== V3 Batch 1: CO2outgas after Fg drop ===")
for t in [190, 195, 196, 198, 200, 202, 204, 206, 208, 210, 215, 220, 225]:
    row = d[d.time_h <= t].iloc[-1]
    print(f"t={t}: CO2={row['CO2outgas']:.3f} Fg={row['Fg']:.0f} S={row['S']:.4f} P={row['P']:.2f} "
          f"DO2={row['DO2']:.1f} pH={row['pH']:.2f} T={row['T']:.2f}")

print("\n=== V3 Batch 1: max CO2outgas ===")
print(f"Max CO2outgas = {d['CO2outgas'].max():.3f} at t={d.loc[d['CO2outgas'].idxmax(), 'time_h']:.1f}")
print(f"CO2outgas range after t=200: {d[d.time_h > 200]['CO2outgas'].min():.3f} ~ {d[d.time_h > 200]['CO2outgas'].max():.3f}")

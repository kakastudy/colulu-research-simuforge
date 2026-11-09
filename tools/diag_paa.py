# -*- coding: utf-8 -*-
"""PAA/NH3/DO2 末端轨迹对比。"""
import sys
import pandas as pd
import numpy as np

batch = int(sys.argv[1]) if len(sys.argv) > 1 else 1
sim = pd.read_csv(f"data/processed/sim_batch_{batch:02d}.csv")
v3 = pd.read_csv(f"data/processed/batches/batch_{batch:02d}.csv")

print(f"--- batch {batch}: PAA / NH3 / DO2 / P at key times ---")
for t in [10, 40, 80, 120, 160, 200, 210, 220, 226]:
    s = sim[sim.time_h <= t].iloc[-1]
    v = v3[v3.time_h <= t].iloc[-1]
    paa_off = v["PAA_offline"]
    nh3_off = v["NH3_offline"]
    paa_off_s = f"{paa_off:8.1f}" if not pd.isna(paa_off) else "     NaN"
    nh3_off_s = f"{nh3_off:8.1f}" if not pd.isna(nh3_off) else "     NaN"
    print(f"  t={t:6.1f}  simPAA={s['PAA']:8.1f} v3PAAoff={paa_off_s}  simNH3={s['NH3']:8.1f} v3NH3off={nh3_off_s}  "
          f"simDO2={s['DO2']:6.2f} v3DO2={v['DO2']:6.2f}  simP={s['P']:7.2f} v3P={v['P']:7.2f}  "
          f"Fpaa={v['Fpaa']:5.2f} Foil={v['Foil']:6.1f}")

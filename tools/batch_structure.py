# -*- coding: utf-8 -*-
"""100 批结构分析：批次长度、终末收获阶段、Fremoved 模式。"""
import glob
import pandas as pd
import numpy as np

rows = []
for f in sorted(glob.glob("data/processed/batches/batch_*.csv")):
    b = int(f.split("batch_")[1].split(".")[0])
    d = pd.read_csv(f, usecols=["time_h", "V", "P", "Fremoved"])
    last_fr = d["Fremoved"].iloc[-1]
    nz_fr = (d["Fremoved"] != 0).sum()
    rows.append({
        "batch": b, "n": len(d), "t_end": d["time_h"].iloc[-1],
        "fr_min": d["Fremoved"].min(), "fr_max": d["Fremoved"].max(),
        "nz_fr": nz_fr, "last_fr": last_fr,
        "V_end": d["V"].iloc[-1], "P_end": d["P"].iloc[-1],
    })
r = pd.DataFrame(rows)
print("=== batch length distribution ===")
print(r["n"].describe().to_string())
print("\n=== batches with non-zero Fremoved at LAST row (final harvest in CSV?) ===")
fin = r[r["last_fr"] != 0]
print("count:", len(fin))
if len(fin):
    print(fin.to_string(index=False))
print("\n=== batches with |Fremoved|>0 anywhere ===")
print("count:", (r["nz_fr"] > 0).sum(), "of", len(r))
print("\n=== t_end distribution ===")
print(r["t_end"].describe().to_string())
print("\n=== sample: batch 3 (longest) tail ===")
d3 = pd.read_csv("data/processed/batches/batch_03.csv", usecols=["time_h", "V", "P", "Fremoved"])
print(d3.tail(8).to_string(index=False))
print("\n=== batch 3 Fremoved non-zero window ===")
nz = d3[d3["Fremoved"] != 0]
print("count:", len(nz), "t range:", nz["time_h"].min(), "-", nz["time_h"].max())

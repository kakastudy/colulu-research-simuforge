# -*- coding: utf-8 -*-
"""调试：批次产率结构分析。"""
import pandas as pd
import numpy as np

df = pd.read_csv("data/processed/batches/batch_01.csv")
stats = pd.read_csv("100_Batches_IndPenSim/Mendeley_data/100_Batches_IndPenSim_Statistics.csv")
s1 = stats.iloc[0]
print("=== stats batch1 ===")
print(s1.to_string())
print("stats units: harvested_during_kg=1.0664e6 -> if kg: 1066 t (impossible); so values are grams\n")

print("=== Fremoved profile (non-zero segments) ===")
fr = df["Fremoved"]
nz = df[fr != 0]
print("non-zero rows:", len(nz), "sign:", np.sign(nz["Fremoved"]).unique())
if len(nz):
    print(nz[["time_h", "Fremoved", "V", "P"]].head(10).to_string(index=False))
    print("...")
    print(nz[["time_h", "Fremoved", "V", "P"]].tail(10).to_string(index=False))

print("\n=== V*P trajectory milestones ===")
df["VP"] = df["V"] * df["P"]
for t in [0.2, 50, 100, 150, 200, 221.2, 226.0]:
    row = df[df["time_h"] == t]
    if len(row):
        r = row.iloc[0]
        print(f"t={t:6.1f}  V={r['V']:9.0f}  P={r['P']:7.3f}  V*P={r['VP']:11.0f}")

print("\n=== where V*P = stats end (1.72e6)? ===")
target = s1["Penicllin_harvested_end_of_batch (kg)"]
# 假设统计值为克
target_g = target  # 1.72e6
near = df[(df["VP"] - target_g).abs() < 200000]
print(near[["time_h", "V", "P", "VP"]].to_string(index=False) if len(near) else "no near match")

print("\n=== max/min V, P ===")
print("V range:", df["V"].min(), "-", df["V"].max())
print("P range:", df["P"].min(), "-", df["P"].max())

print("\n=== batch lengths across all batches ===")
import glob
rows = []
for f in sorted(glob.glob("data/processed/batches/batch_*.csv")):
    d = pd.read_csv(f, usecols=["time_h", "V", "P", "Fremoved"])
    rows.append((f.split("batch_")[1].split(".")[0], len(d), d["time_h"].iloc[-1],
                 d["Fremoved"].min(), d["Fremoved"].max()))
r = pd.DataFrame(rows, columns=["batch", "n", "t_end", "fr_min", "fr_max"])
print(r.head(12).to_string(index=False))
print("...")
print(r.tail(8).to_string(index=False))
print("\nbatches with |fr|>0:", int((r["fr_min"] < 0).sum()), "of", len(r))

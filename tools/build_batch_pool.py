# -*- coding: utf-8 -*-
"""PH1-a：批池分层划分（60 训练 / 28 验证 / 12 黄金）→ data/processed/batch_pool.json。

分层维度：FaultFlag(0/1) × 产量四分位；种子固定保证可复现；黄金集只评不训。
统计表头单位为 kg 但数值为 g（T7 已登记）；统一换算 Mg。
"""
import json
import os

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADMIN = os.path.join(ROOT, "100_Batches_IndPenSim", "Mendeley_data",
                     "100_Batches_IndPenSim_Statistics.csv")
GOLDEN = [8, 11, 16, 22, 23, 27, 36, 55, 60, 80, 91, 92]

stats = pd.read_csv(ADMIN, encoding="utf-8")
stats = stats.rename(columns={
    "Batch ref": "batch",
    "Penicllin_harvested_during_batch(kg)": "harv_g",
    "Penicllin_harvested_end_of_batch (kg)": "end_g",
    "Penicllin_yield_total (kg)": "yield_g",
    "Fault ref(0-NoFault 1-Fault)": "fault",
})
stats["fault"] = stats["fault"].astype(int)
stats["yield_Mg"] = stats["yield_g"] / 1e6
stats["is_golden"] = stats["batch"].isin(GOLDEN)

assert len(stats) == 100 and set(stats["batch"]) == set(range(1, 101))
n_fault = int(stats["fault"].sum())
print(f"总批数 100；故障批 {n_fault}：{sorted(stats.loc[stats.fault == 1, 'batch'])}")
pool = stats[~stats["is_golden"]].copy()
assert len(pool) == 88

# 分层（故障 × 产量四分位）+ 固定种子
pool["q"] = pd.qcut(pool["yield_Mg"], 4, labels=False, duplicates="drop")
rng = np.random.default_rng(20261027)
train, val = [], []
for (f, q), grp in pool.groupby(["fault", "q"]):
    idx = grp["batch"].tolist()
    rng.shuffle(idx)
    k_tr = round(len(idx) * 60 / 88)
    train += idx[:k_tr]
    val += idx[k_tr:]
train, val = sorted(train), sorted(val)
assert len(train) == 60 and len(val) == 28 and not (set(train) & set(val))

out = {
    "version": 1, "sealed": "2026-10-27", "seed": 20261027,
    "split_policy": "stratify(fault, yield_quartile) 60/28；黄金 12 只评不训",
    "golden": sorted(GOLDEN), "train": train, "validation": val,
    "yield_Mg_lookup": {str(int(r.batch)): round(r.yield_Mg, 4)
                        for r in stats.itertuples()},
    "fault_lookup": {str(int(r.batch)): int(r.fault) for r in stats.itertuples()},
}
dst = os.path.join(ROOT, "data", "processed", "batch_pool.json")
with open(dst, "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
ft = out["fault_lookup"]
print(f"训练 60 批（含故障 {sum(ft[str(b)] for b in train)}）；验证 28 批（含故障 {sum(ft[str(b)] for b in val)}）")
print("Saved:", dst)

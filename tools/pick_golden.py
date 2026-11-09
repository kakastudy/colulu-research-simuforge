# -*- coding: utf-8 -*-
"""选定黄金集：10 正常批（产率分布分层）+ 2 故障批。只增不减。"""
import pandas as pd

m = pd.read_csv("data/processed/batches_manifest.csv")
norm = m[m["fault_flag"] == 0].copy()
fault = m[m["fault_flag"] == 1].copy()

# 正常批按 total_in_vessel_g 分层：10%, 30%, 50%, 70%, 90% 附近各取，共 10 个
norm["pct"] = norm["total_in_vessel_g"].rank(pct=True)
targets = [0.10, 0.25, 0.40, 0.50, 0.60, 0.75, 0.85, 0.90, 0.95, 0.98]
picked = []
for p in targets:
    near = norm.iloc[(norm["pct"] - p).abs().argsort()[:1]]
    picked.append(int(near["batch"].iloc[0]))
picked = sorted(set(picked))
# 补足到 10 个
for b in norm["batch"]:
    if len(picked) >= 10:
        break
    if b not in picked:
        picked.append(int(b))
picked = sorted(picked)[:10]

fault_picked = sorted(fault["batch"].tolist())[:2]

golden = {
    "normal": picked,
    "fault": fault_picked,
    "criteria": "正常批按产率分层（10%-98% 分位）；故障批取前 2 个；只增不减",
}
print("golden normal:", picked)
print("golden fault:", fault_picked)
print("yield spread of picked normal:",
      [round(float(m.loc[m["batch"] == b, "total_in_vessel_g"].iloc[0]) / 1000, 1) for b in picked])

import json
with open("data/processed/golden_set.json", "w", encoding="utf-8") as f:
    json.dump(golden, f, ensure_ascii=False, indent=2)
print("saved golden_set.json")
